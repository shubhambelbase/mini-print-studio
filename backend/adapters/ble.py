import asyncio
import logging
from collections import deque
from typing import List, Dict, Any, Optional
from backend.adapters.base import BasePrinterAdapter

try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

logger = logging.getLogger("BLEPrinterAdapter")


class BLEPrinterAdapter(BasePrinterAdapter):
    """
    Bluetooth Low Energy (BLE) printer adapter using Bleak.
    """
    KNOWN_WRITE_UUIDS = [
        "0000ae01-0000-1000-8000-00805f9b34fb",  # iPrint main (SC03h / FC02 / D1)
        "0000ae3b-0000-1000-8000-00805f9b34fb",  # iPrint alternate
        "49535343-8841-43f4-a8d4-ecbe34729bb3",  # ISSC Transparent UART
        "49535343-1e4d-4bd9-ba61-23c647249616",
        "e7810a71-73ae-499d-8c15-faa9aef0c3f2",  # Another common thermal printer
        "0000ffe1-0000-1000-8000-00805f9b34fb",  # HM-10 UART
        "00002af1-0000-1000-8000-00805f9b34fb",
        "6e400002-b5a3-f393-e0a9-e50e24dcca9e",  # Nordic UART Service Write
        "0000ff02-0000-1000-8000-00805f9b34fb",
        "0000ff01-0000-1000-8000-00805f9b34fb",
        "000018f0-0000-1000-8000-00805f9b34fb",
    ]

    IPRINT_NAME_MARKERS = (
        "iprint", "cat", "gb01", "gb02", "walkprint", "funprint",
        "sc03h", "fc02", "d1", "pocket", "mini", "thermal"
    )

    @classmethod
    def detect_protocol(cls, device_name: str) -> str:
        """
        Infers the printer protocol from the device name.
        iPrint/Cat printers (SC03h, GB01/02, WalkPrint, FunPrint...) use the
        proprietary binary protocol; everything else defaults to ESC/POS.
        """
        name = (device_name or "").lower()
        if any(marker in name for marker in cls.IPRINT_NAME_MARKERS):
            return "iprint"
        return "escpos"

    def __init__(self, address: str, protocol: str = "escpos"):
        super().__init__(address, protocol)
        self.client: Optional[Any] = None
        self.write_uuid: Optional[str] = None
        self.write_uuids: List[str] = []
        self.notify_uuids: List[str] = []
        self.last_notify_payload: Optional[bytes] = None
        self.device_info: Dict[str, Any] = {}
        # Ring buffer of raw wire activity (direction + hex) for the debug view.
        self.packet_trace: deque = deque(maxlen=800)
        self.last_payload: Optional[bytes] = None
        self._io_lock = asyncio.Lock()
        self._watchdog_task: Optional[asyncio.Task] = None
        self._device_info_event: Optional[asyncio.Event] = None

    def _record_trace(self, direction: str, data: bytes, max_len: int = 900):
        try:
            text = data[:max_len].hex()
            self.packet_trace.append({"dir": direction, "hex": text, "n_bytes": len(data)})
        except Exception:
            pass

    @classmethod
    def parse_device_info_payload(cls, payload: bytes) -> Dict[str, Any]:
        """Best-effort decode of a 0xA8 response (firmware/model strings vary)."""
        info: Dict[str, Any] = {"raw": payload.hex()}
        try:
            text = payload.decode("utf-8", errors="replace").strip("\x00\r\n ")
            if text:
                info["text"] = text
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if len(lines) == 1 and "," in text:
                    lines = [ln.strip() for ln in text.split(",") if ln.strip()]
                if lines:
                    info["lines"] = lines
                    info["model"] = lines[0]
                    if len(lines) > 1:
                        info["firmware"] = lines[1]
        except Exception:
            pass
        return info

    async def scan(self) -> List[Dict[str, Any]]:
        if not BLEAK_AVAILABLE:
            logger.warning("Bleak library is not installed.")
            return []

        devices_found = []
        try:
            devices = await BleakScanner.discover(timeout=3.0)
            for d in devices:
                name = d.name or ""
                # Real thermal printers always advertise a recognizable name
                # (e.g. "SC03h-E0FE"); unnamed devices (phones, TVs, trackers)
                # are not connectable and would only stall the user.
                if not name or name == "Unknown BLE Device":
                    continue
                devices_found.append({
                    "id": f"ble-{d.address}",
                    "name": name,
                    "connection_type": "ble",
                    "address": d.address,
                    "protocol": self.detect_protocol(name),
                    "printable_width_px": 384,
                    "paper_width_mm": 58,
                    "status": "available",
                    "rssi": getattr(d, "rssi", -70),
                    "is_default": False
                })
        except Exception as e:
            logger.warning(f"BLE scanner notice (Bluetooth radio may be off or disabled): {e}")
            return []
        return devices_found

    async def connect(self) -> bool:
        if not BLEAK_AVAILABLE:
            raise RuntimeError("Bleak library is not available.")

        try:
            # Hard cap on the entire connect+discovery+notify sequence so the
            # UI never waits forever on an unreachable device.
            await asyncio.wait_for(self._connect_and_discover(), timeout=20)
            return self.connected
        except asyncio.TimeoutError:
            logger.error(f"BLE connect to {self.address} timed out after 20s.")
        except Exception as e:
            logger.error(f"Failed to connect to BLE printer {self.address}: {e}")

        # Clean up any partially-established link (e.g. a notify subscription
        # rejection) so the failed adapter never leaves a live socket behind.
        self._stop_device_watchdog()
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass
            self.client = None
        self.connected = False
        return False

    async def _connect_and_discover(self):
        self.client = BleakClient(self.address, timeout=10.0)
        await self.client.connect()
        self.connected = self.client.is_connected

        if self.connected:
            self.write_uuids = []
            self.notify_uuids = []
            # Discover services and find writable and notify characteristics
            for service in self.client.services:
                # Skip standard Bluetooth SIG services (0x1800 to 0x18FF)
                if service.uuid.startswith("000018"):
                    continue
                    
                for char in service.characteristics:
                    props = [str(p).lower() for p in char.properties]
                    if "write-without-response" in props or "write" in props:
                        self.write_uuids.append(char.uuid)
                        logger.info(f"Discovered candidate BLE write characteristic: {char.uuid} in service {service.uuid}")
                    if "notify" in props or "indicate" in props:
                        self.notify_uuids.append(char.uuid)
                        logger.info(f"Discovered candidate BLE notify characteristic: {char.uuid} in service {service.uuid}")
            
            if self.write_uuids:
                def uuid_priority(u):
                    u_lower = u.lower()
                    for i, known in enumerate(self.KNOWN_WRITE_UUIDS):
                        if known.lower() in u_lower or u_lower.startswith(known.lower()[:8]):
                            return i
                    return 999
                self.write_uuids.sort(key=uuid_priority)
                self.write_uuid = self.write_uuids[0]
                logger.info(f"Initially selected BLE write characteristic: {self.write_uuid}")

                # Enable notifications if required by printer to unlock writes.
                # Also captures device state (battery/paper) where the firmware reports it.
                def notify_callback(sender, data):
                    try:
                        raw = bytes(data)
                        self.last_notify_payload = raw
                        self._record_trace("R", raw)
                        # A 0xA8 response carries model/firmware info; capture it.
                        if len(raw) >= 8 and raw[0] == 0x51 and raw[1] == 0x78 and raw[2] == 0xA8:
                            length = raw[4] | (raw[5] << 8)
                            self.device_info = self.parse_device_info_payload(raw[6:6 + length])
                        if self._device_info_event is not None:
                            self._device_info_event.set()
                    except Exception:
                        pass

                subscribed_any = False
                for n_uuid in self.notify_uuids:
                    try:
                        await self.client.start_notify(n_uuid, notify_callback)
                        subscribed_any = True
                        logger.info(f"Subscribed to notifications on {n_uuid}")
                    except Exception as e:
                        logger.warning(f"Failed to subscribe to notify characteristic {n_uuid}: {e}")

                # The iPrint printer uses the notify subscription as a "host is
                # alive" signal; per the protocol doc a device that advertises
                # notify characteristics but rejects every subscription will
                # silently ignore writes. Fail the connect up front instead of
                # letting writes fail confusingly later. Clones that expose no
                # notify characteristics at all are allowed through.
                if (self.protocol == "iprint" and self.notify_uuids and not subscribed_any):
                    raise RuntimeError(
                        "iPrint printer advertised notify characteristics but rejected all "
                        "subscriptions; refusing to connect without the mandatory notify link."
                    )

                # iPrint specifics: query model/firmware (0xA8) and start the
                # keep-alive watchdog (periodic 0xA3 state ping).
                if self.protocol == "iprint" and self.write_uuid:
                    await self._query_device_info()
                    self._start_device_watchdog()

        return self.connected

    async def _query_device_info(self, timeout: float = 2.5):
        """Sends 0xA8 (Get Device Info) and waits briefly for a response."""
        from backend.protocols.iprint import IPrintProtocol
        self._device_info_event = asyncio.Event()
        try:
            if not self.client or not self.client.is_connected:
                return
            await self.client.write_gatt_char(self.write_uuid, IPrintProtocol.format_message(0xA8, []))
            self._record_trace("W", IPrintProtocol.format_message(0xA8, []))
            await asyncio.wait_for(self._device_info_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.info("Device info query (0xA8) timed out; continuing without it.")
        except Exception as e:
            logger.debug(f"Device info query failed: {e}")
        finally:
            self._device_info_event = None

    # ------------------------------------------------------------------ #
    # Keep-alive watchdog (detects stale sockets proactively, doc 13.2)
    # ------------------------------------------------------------------ #

    def _start_device_watchdog(self):
        self._stop_device_watchdog()
        self._watchdog_task = asyncio.get_event_loop().create_task(self._watchdog_loop())

    def _stop_device_watchdog(self):
        if self._watchdog_task is not None:
            self._watchdog_task.cancel()
            self._watchdog_task = None

    async def _watchdog_loop(self, interval: float = 30.0):
        """Pings the printer with 0xA3 [0x00]. If the write fails the socket is
        stale: tear the link down so the app reports a clean disconnect."""
        from backend.protocols.iprint import IPrintProtocol
        packet = IPrintProtocol.format_message(0xA3, [0x00])
        while True:
            await asyncio.sleep(interval)
            if not self.connected or self.client is None or not self.client.is_connected:
                break
            # Never interleave a keep-alive into an in-flight job stream.
            if self._io_lock.locked():
                continue
            try:
                await asyncio.wait_for(
                    self.client.write_gatt_char(self.write_uuid, packet), timeout=10.0
                )
                self._record_trace("W", packet)
            except asyncio.TimeoutError:
                logger.error("Keep-alive ping timed out — BLE link is likely stale.")
            except Exception as e:
                logger.error(f"Keep-alive ping failed ({e}) — marking connection as stale.")
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
                self.connected = False
                break

    async def disconnect(self) -> bool:
        self._stop_device_watchdog()
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting BLE client: {e}")
        self.connected = False
        self.client = None
        return True

    async def send_bytes(self, data: bytes) -> bool:
        if not self.connected or not self.client or not self.client.is_connected:
            raise ConnectionError("BLE Printer is not connected.")

        self.last_payload = data
        self._record_trace("W", data, max_len=1500)

        async with self._io_lock:
            return await self._send_bytes_locked(data)

    async def _send_bytes_locked(self, data: bytes) -> bool:

        if not self.write_uuids and self.client.services:
            for service in self.client.services:
                if service.uuid.startswith("000018"): continue
                for char in service.characteristics:
                    props = [str(p).lower() for p in char.properties]
                    if "write-without-response" in props or "write" in props:
                        self.write_uuids.append(char.uuid)

        if not self.write_uuids:
            raise ConnectionError("Could not find a writable GATT characteristic on this BLE printer.")

        # Prioritize known printer UUIDs
        def uuid_priority(u):
            u_lower = u.lower()
            for i, known in enumerate(self.KNOWN_WRITE_UUIDS):
                if known.lower() in u_lower or u_lower.startswith(known.lower()[:8]):
                    return i
            return 999
            
        self.write_uuids.sort(key=uuid_priority)

        # iPrint / SC03h (d1 profile) prefers 180 bytes chunk size
        chunk_size = 180

        # Long iPrint jobs: the SC03h firmware buffer is tiny and silently
        # drops the tail of long payloads. Send whole-packet bursts with a
        # drain pause between them so the thermal head can keep up.
        if self.protocol == "iprint" and len(data) > 20000:
            from backend.protocols.iprint import IPrintProtocol
            segments = IPrintProtocol.split_into_segments(data, segment_size=4096)
            for seg_index, segment in enumerate(segments):
                await self._write_chunks(segment, chunk_size, chunk_delay=0.025)
                if seg_index < len(segments) - 1:
                    await asyncio.sleep(0.6)
            return True

        # Default path: pace chunks more conservatively for large payloads.
        if len(data) > 20000:
            chunk_delay = 0.025
        else:
            chunk_delay = 0.01

        # Try to write to the first working characteristic
        for char_uuid in self.write_uuids:
            chunks_written = 0
            try:
                for i in range(0, len(data), chunk_size):
                    chunk = data[i:i + chunk_size]
                    try:
                        # Let bleak determine the default response mode based on characteristic properties
                        await self.client.write_gatt_char(char_uuid, chunk)
                        chunks_written += 1
                    except Exception as char_exc:
                        if "Access Denied" in str(char_exc) or "Not Supported" in str(char_exc):
                            raise char_exc # Trigger outer except to try next characteristic
                        logger.warning(f"Failed to write chunk to {char_uuid}: {char_exc}")
                        raise char_exc
                    await asyncio.sleep(chunk_delay)
                
                # If we succeeded, update the active write_uuid
                if self.write_uuid != char_uuid:
                    self.write_uuid = char_uuid
                    logger.info(f"Switched to successful BLE write characteristic: {char_uuid}")
                return True
            except Exception as e:
                # If some chunks already reached this characteristic, the printer
                # has received partial data; retrying the full payload on another
                # characteristic would duplicate/garble it, so fail hard instead.
                if chunks_written > 0:
                    raise ConnectionError(
                        f"BLE write failed after {chunks_written} chunk(s) on {char_uuid}; "
                        f"partial payload already sent: {e}"
                    )
                logger.warning(f"Failed to write to characteristic {char_uuid}: {e}")
                continue
                
        raise ConnectionError("Failed to write to any of the discovered writable characteristics.")

    async def _write_chunks(self, payload: bytes, chunk_size: int, chunk_delay: float):
        """Writes a payload to the best matching characteristic in chunks."""
        for char_uuid in self.write_uuids:
            chunks_written = 0
            try:
                for i in range(0, len(payload), chunk_size):
                    chunk = payload[i:i + chunk_size]
                    try:
                        await self.client.write_gatt_char(char_uuid, chunk)
                        chunks_written += 1
                    except Exception as char_exc:
                        if "Access Denied" in str(char_exc) or "Not Supported" in str(char_exc):
                            raise char_exc
                        logger.warning(f"Failed to write chunk to {char_uuid}: {char_exc}")
                        raise char_exc
                    await asyncio.sleep(chunk_delay)
                if self.write_uuid != char_uuid:
                    self.write_uuid = char_uuid
                    logger.info(f"Switched to successful BLE write characteristic: {char_uuid}")
                return
            except Exception as e:
                if chunks_written > 0:
                    raise ConnectionError(
                        f"BLE write failed after {chunks_written} chunk(s) on {char_uuid}; "
                        f"partial payload already sent: {e}"
                    )
                logger.warning(f"Failed to write to characteristic {char_uuid}: {e}")
                continue
        raise ConnectionError("Failed to write to any of the discovered writable characteristics.")

    def is_connected(self) -> bool:
        return self.connected and self.client is not None and self.client.is_connected

    def get_device_info(self) -> Dict[str, Any]:
        """Model/firmware info captured from the 0xA8 response (best-effort)."""
        return self.device_info

    def get_trace(self) -> List[Dict[str, Any]]:
        """Recent raw wire activity for the debug view."""
        return list(self.packet_trace) if self.packet_trace else []

    # ------------------------------------------------------------------ #
    # Device status (best-effort parsing of printer notifications)
    # ------------------------------------------------------------------ #

    def get_device_status(self) -> Dict[str, Any]:
        """
        Parses the most recent notify payload for battery/paper information.
        iPrint responses are wrapped in the standard [0x51,0x78,...] envelope;
        the payload layout varies between firmwares, so every field is optional
        and reported conservatively.
        """
        if not self.last_notify_payload:
            return {}
        payload = self.last_notify_payload

        # Strip the packet envelope if present: 51 78 op 00 len 00 [payload] crc ff
        data = payload
        if len(payload) >= 8 and payload[0] == 0x51 and payload[1] == 0x78:
            length = payload[4] | (payload[5] << 8)
            data = payload[6:6 + length]

        return self._parse_state_payload(data)

    @staticmethod
    def _parse_state_payload(data: bytes) -> Dict[str, Any]:
        info: Dict[str, Any] = {}
        if len(data) == 0:
            return info

        # First byte is usually a device-state bitfield; expose raw for debugging.
        state_byte = data[0]
        info["raw"] = data.hex()

        # Battery: where the firmware reports it as a 0-100 value.
        if len(data) >= 2:
            battery = data[1]
            if 0 < battery <= 100:
                info["battery_level"] = battery

        # Paper: best-effort bit test on the state byte.
        # Bit 2 set often means paper-out on iPrint-style firmware.
        if state_byte & 0x04:
            info["paper_present"] = False
        else:
            info["paper_present"] = True

        # Some clones echo the requested state back as 0x00 = idle/ok.
        if state_byte == 0x00:
            info["paper_present"] = True

        return info
