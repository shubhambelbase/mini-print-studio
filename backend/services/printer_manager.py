import os
import json
import asyncio
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

from backend.models.printer import PrinterDevice, PrinterStatus, ConnectionRequest
from backend.models.print_job import PrintRequest, PrintJobRecord, ContentBlock
from backend.adapters.base import BasePrinterAdapter
from backend.adapters.ble import BLEPrinterAdapter
from backend.adapters.bluetooth_classic import BluetoothClassicAdapter
from backend.adapters.mock import MockPrinterAdapter
from backend.services.print_engine import PrintEngine
from backend.services.image_processor import ImageProcessor

logger = logging.getLogger("PrinterManager")

TERMINAL_STATUSES = ("completed", "failed", "cancelled")


class PrinterManager:
    """
    Central printer hardware and job lifecycle orchestrator.
    """

    def __init__(self, data_dir: Optional[str] = None):
        # Allow overriding the data directory (e.g. tests use a temp dir so
        # the real local printer profile / history stay untouched).
        self.data_dir = data_dir or os.environ.get("MPS_DATA_DIR", "data")
        self.printers_file = os.path.join(self.data_dir, "printers.json")
        self.history_file = os.path.join(self.data_dir, "history.json")

        self.current_adapter: Optional[BasePrinterAdapter] = None
        self.active_printer_device: Optional[PrinterDevice] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._job_records: Dict[str, PrintJobRecord] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self.active_job_id: Optional[str] = None
        self._send_lock = asyncio.Lock()
        # Live event subscribers (SSE): one asyncio.Queue per client.
        self._subscribers: Set[asyncio.Queue] = set()

    # ------------------------------------------------------------------ #
    # Live event broadcast (SSE)
    # ------------------------------------------------------------------ #

    def _broadcast(self, event: dict):
        """Delivers a JSON event to every connected SSE client (best-effort)."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    async def event_stream(self):
        """
        Async generator for the /api/events SSE endpoint. Yields JSON events
        on job-state transitions and printer connect/disconnect.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            self._subscribers.discard(queue)

    # ------------------------------------------------------------------ #
    # Scan / Connect / Status
    # ------------------------------------------------------------------ #

    async def scan_printers(self, mode: Optional[str] = None) -> List[PrinterDevice]:
        """
        Scans for real Bluetooth Low Energy printers only.
        Mock/virtual devices are never included in scan results.
        """
        devices: List[PrinterDevice] = []

        try:
            ble_adapter = BLEPrinterAdapter(address="")
            ble_devs = await ble_adapter.scan()
            for d in ble_devs:
                devices.append(PrinterDevice(**d))
        except Exception as e:
            logger.warning(f"BLE scan exception: {e}")

        return devices

    async def connect_printer(self, request: ConnectionRequest) -> PrinterStatus:
        """
        Connects to a specific printer device and persists it as the default profile.
        """
        # Disconnect current if connected
        if self.current_adapter and self.current_adapter.is_connected():
            await self.current_adapter.disconnect()

        conn_type = (request.connection_type or "ble").lower()
        address = request.address or ""
        protocol = request.protocol or "escpos"

        if conn_type == "ble":
            self.current_adapter = BLEPrinterAdapter(address=address, protocol=protocol)
        elif conn_type == "bluetooth_classic":
            self.current_adapter = BluetoothClassicAdapter(address=address, protocol=protocol)
        elif conn_type == "mock":
            self.current_adapter = MockPrinterAdapter(address=address or "mock-1", protocol=protocol)
        else:
            raise ValueError(f"Unsupported connection type: {conn_type}")

        success = await self.current_adapter.connect()
        if success:
            if conn_type == "mock":
                name = "Mock Thermal Printer (Simulator)"
            else:
                name = f"{conn_type.upper()} Printer ({address[:8]})"
            printable_width_px = 384
            paper_width_mm = 58

            self.active_printer_device = PrinterDevice(
                id=request.printer_id,
                name=name,
                connection_type=conn_type,
                address=address,
                protocol=protocol,
                printable_width_px=printable_width_px,
                paper_width_mm=paper_width_mm,
                status="connected",
                is_default=True
            )
            self._save_connection_profile(self.active_printer_device)
            self._broadcast({"type": "printer", "connected": True, "address": address})
            return self.get_status()
        else:
            self.active_printer_device = None
            self._broadcast({"type": "printer", "connected": False, "address": address})
            return PrinterStatus(
                connected=False,
                message=f"Failed to connect to printer at address {address}."
            )

    async def disconnect_printer(self) -> PrinterStatus:
        if self.current_adapter:
            await self.current_adapter.disconnect()
        if self.active_printer_device:
            self.active_printer_device.status = "disconnected"
        self._broadcast({"type": "printer", "connected": False, "address": self.active_printer_device.address if self.active_printer_device else None})
        return self.get_status()

    def get_status(self) -> PrinterStatus:
        is_conn = self.current_adapter.is_connected() if self.current_adapter else False
        battery_level = None
        paper_present = True
        device_info = None
        if is_conn and isinstance(self.current_adapter, BLEPrinterAdapter):
            try:
                dev_status = self.current_adapter.get_device_status()
                if dev_status.get("battery_level") is not None:
                    battery_level = dev_status["battery_level"]
                if dev_status.get("paper_present") is not None:
                    paper_present = dev_status["paper_present"]
            except Exception as e:
                logger.debug(f"Could not read BLE device status: {e}")
            device_info = self.current_adapter.get_device_info() or None
        return PrinterStatus(
            connected=is_conn,
            current_printer=self.active_printer_device if is_conn else None,
            active_job_id=self.active_job_id,
            queue_length=self.queue_length(),
            paper_present=paper_present,
            battery_level=battery_level,
            device_info=device_info,
            message="Printer connected and ready" if is_conn else "No printer connected"
        )

    # ------------------------------------------------------------------ #
    # Print queue
    # ------------------------------------------------------------------ #

    def queue_length(self) -> int:
        return self._queue.qsize() + (1 if self.active_job_id else 0)

    def _ensure_worker(self):
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.get_event_loop().create_task(self._worker())

    async def submit_print_job(self, print_req: PrintRequest) -> PrintJobRecord:
        """
        Enqueues a print job. The queue worker renders, sends to hardware,
        and records the terminal status asynchronously.
        """
        if not self.current_adapter or not self.current_adapter.is_connected():
            raise ConnectionError("No printer connected. Please connect to a physical printer.")

        job = PrintJobRecord(
            id=f"job-{uuid.uuid4().hex[:8]}",
            title=print_req.title or "Untitled Print Job",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            content_types=list(set([b.type for b in print_req.blocks])),
            printer_name=self.active_printer_device.name if self.active_printer_device else "Unknown",
            width_px=0,
            height_px=0,
            status="queued",
            queue_position=self._queue.qsize() + 1,
            blocks=[b.model_dump() for b in print_req.blocks]
        )
        self._job_records[job.id] = job
        self._queue.put_nowait((job.id, print_req.model_copy(deep=True)))
        self._ensure_worker()
        self._broadcast({"type": "job", "job_id": job.id, "status": "queued", "title": job.title})
        return job

    def get_job_record(self, job_id: str) -> Optional[PrintJobRecord]:
        return self._job_records.get(job_id)

    def get_queue_status(self) -> Dict[str, Any]:
        active = self._job_records.get(self.active_job_id) if self.active_job_id else None
        queued_ids = []
        for item in list(self._queue._queue):
            queued_ids.append(item[0] if isinstance(item, tuple) else item)
        queued = [self._job_records[i] for i in queued_ids if i in self._job_records]
        return {
            "active_job": active,
            "queued": queued,
            "queue_length": self.queue_length()
        }

    def cancel_job(self, job_id: Optional[str] = None) -> List[str]:
        """
        Cancels a specific job, or (when no id is given) the active job and
        everything queued behind it. Returns the cancelled job ids.
        """
        cancelled = []
        targets = []
        if job_id:
            targets = [job_id]
        else:
            if self.active_job_id:
                targets.append(self.active_job_id)
            for item in list(self._queue._queue):
                item_id = item[0] if isinstance(item, tuple) else item
                targets.append(item_id)

        for tid in targets:
            rec = self._job_records.get(tid)
            if rec and rec.status in ("queued", "preparing", "printing"):
                rec.status = "cancelled"
                cancelled.append(tid)
        return cancelled

    async def _worker(self):
        """Processes queued jobs sequentially."""
        while True:
            item = await self._queue.get()
            job_id, print_req = item if isinstance(item, tuple) else (item, None)
            self.active_job_id = job_id
            try:
                job = self._job_records.get(job_id)
                if job is None or print_req is None:
                    continue
                await self._process_job(job, print_req)
            except Exception as e:
                logger.exception(f"Unexpected error processing job {job_id}: {e}")
                rec = self._job_records.get(job_id)
                if rec and rec.status not in TERMINAL_STATUSES:
                    rec.status = "failed"
                    rec.error_message = str(e)
                    self.save_job_history(rec)
                    self._broadcast({"type": "job", "job_id": job_id, "status": "failed", "title": rec.title})
            finally:
                self.active_job_id = None
                self._queue.task_done()

    async def _process_job(self, job: PrintJobRecord, print_req: PrintRequest):
        if job.status == "cancelled":
            return

        job.status = "preparing"
        self._broadcast({"type": "job", "job_id": job.id, "status": "preparing", "title": job.title})
        try:
            if self.active_printer_device and self.active_printer_device.printable_width_px:
                width_px = self.active_printer_device.printable_width_px
            else:
                width_px = print_req.width_px or 384
            margin_px = print_req.margin_px if print_req.margin_px is not None else 8

            raw = print_req.raw_payload
            if raw:
                # Pre-built payloads (e.g. density calibration) skip the
                # block rendering stage entirely.
                rendered_image = None
                job.width_px = width_px
                job.height_px = 0
            else:
                rendered_image = PrintEngine.render_blocks_to_image(
                    blocks=print_req.blocks,
                    target_width_px=width_px,
                    margin_px=margin_px
                )
                job.width_px = rendered_image.width
                job.height_px = rendered_image.height
                job.preview_url = ImageProcessor.to_base64_png(rendered_image)
            await asyncio.sleep(0)

            if job.status == "cancelled":
                return

            protocol = self.active_printer_device.protocol if self.active_printer_device else "escpos"
            printer_cfg = self._load_printer_settings()
            density = printer_cfg["density"]
            copies = max(1, print_req.copies or 1)

            if job.status == "cancelled":
                return

            job.status = "printing"
            self._broadcast({"type": "job", "job_id": job.id, "status": "printing", "title": job.title})
            if not self.current_adapter or not self.current_adapter.is_connected():
                raise ConnectionError("No printer connected. Please connect to a physical printer.")

            # Cut command only belongs on the final copy.
            # None-check (not "or 3") so an explicit feed_lines=0 really means
            # "no trailing feed" instead of silently becoming the default.
            feed_lines = print_req.feed_lines if print_req.feed_lines is not None else 3
            if raw:
                base_bytes = raw
                final_bytes = raw
            else:
                base_bytes = PrintEngine.generate_protocol_bytes(
                    image=rendered_image,
                    protocol=protocol,
                    feed_lines=feed_lines,
                    cut_paper=False,
                    density=density,
                    feed_dots=printer_cfg["tear_bar_feed_dots"]
                )
                final_bytes = base_bytes
                if print_req.cut_paper:
                    final_bytes = PrintEngine.generate_protocol_bytes(
                        image=rendered_image,
                        protocol=protocol,
                        feed_lines=feed_lines,
                        cut_paper=True,
                        density=density,
                        feed_dots=printer_cfg["tear_bar_feed_dots"]
                    )

            try:
                async with self._send_lock:
                    for _ in range(max(0, copies - 1)):
                        # Each copy is a self-contained job stream (wake + init
                        # + rows), so it is safe to stop between copies without
                        # ever truncating a packet mid-stream.
                        if job.status == "cancelled":
                            break
                        await self.current_adapter.send_bytes(base_bytes)
                    if job.status != "cancelled":
                        await self.current_adapter.send_bytes(final_bytes)
                # A cancel may have arrived mid-print; honour it.
                if job.status != "cancelled":
                    job.status = "completed"
                    job.error_message = None
                self._broadcast({"type": "job", "job_id": job.id, "status": job.status, "title": job.title})
            except Exception as e:
                logger.error(f"Print job failed: {e}")
                if "not connected" in str(e).lower() or isinstance(e, ConnectionError) or "bleak" in str(e).lower():
                    logger.info("Attempting auto-reconnect to recover from stale socket...")
                    try:
                        await self.current_adapter.disconnect()
                        if self.active_printer_device.connection_type == "ble":
                            await self.current_adapter.connect()
                            async with self._send_lock:
                                for _ in range(max(0, copies - 1)):
                                    if job.status == "cancelled":
                                        break
                                    await self.current_adapter.send_bytes(base_bytes)
                                if job.status != "cancelled":
                                    await self.current_adapter.send_bytes(final_bytes)
                            if job.status != "cancelled":
                                job.status = "completed"
                                job.error_message = None
                            self._broadcast({"type": "job", "job_id": job.id, "status": job.status, "title": job.title})
                        else:
                            raise e
                    except Exception as reconnect_e:
                        logger.error(f"Auto-reconnect failed: {reconnect_e}")
                        job.status = "failed"
                        job.error_message = f"Connection lost. Auto-reconnect failed: {reconnect_e}"
                else:
                    job.status = "failed"
                    job.error_message = str(e)
                self._broadcast({"type": "job", "job_id": job.id, "status": job.status, "title": job.title})
        finally:
            if job.status in TERMINAL_STATUSES:
                self.save_job_history(job)

    # ------------------------------------------------------------------ #
    # Profiles & auto-reconnect
    # ------------------------------------------------------------------ #

    def _save_connection_profile(self, device: PrinterDevice):
        """Upserts the connected device into printers.json as the default profile."""
        try:
            profiles = []
            if os.path.exists(self.printers_file):
                try:
                    with open(self.printers_file, "r", encoding="utf-8") as f:
                        profiles = json.load(f)
                except Exception:
                    profiles = []

            new_entry = {
                "id": device.id,
                "name": device.name,
                "connection_type": device.connection_type,
                "address": device.address,
                "protocol": device.protocol,
                "printable_width_px": device.printable_width_px,
                "paper_width_mm": device.paper_width_mm,
                "status": "available",
                "is_default": True
            }

            kept = [p for p in profiles if p.get("address") != device.address]
            for p in kept:
                p["is_default"] = False
            kept.append(new_entry)
            kept = kept[:20]

            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.printers_file, "w", encoding="utf-8") as f:
                json.dump(kept, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save connection profile: {e}")

    def load_default_profile(self) -> Optional[Dict[str, Any]]:
        """Returns the saved default printer profile, if any."""
        if not os.path.exists(self.printers_file):
            return None
        try:
            with open(self.printers_file, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            for p in profiles:
                if p.get("is_default"):
                    return p
            if profiles:
                return profiles[0]
        except Exception as e:
            logger.error(f"Failed to load printer profile: {e}")
        return None

    async def auto_reconnect(self) -> bool:
        """
        Reconnects to the last used real printer (BLE/Classic) at startup.
        Mock profiles are intentionally skipped.
        """
        profile = self.load_default_profile()
        if not profile:
            logger.info("No saved printer profile to reconnect to.")
            return False
        conn_type = profile.get("connection_type")
        if conn_type not in ("ble", "bluetooth_classic"):
            logger.info(f"Skipping auto-reconnect for profile type '{conn_type}'.")
            return False
        try:
            req = ConnectionRequest(
                printer_id=profile.get("id") or f"printer-{uuid.uuid4().hex[:6]}",
                connection_type=conn_type,
                address=profile.get("address"),
                protocol=profile.get("protocol") or "escpos"
            )
            status = await self.connect_printer(req)
            if status.connected:
                logger.info(f"Auto-reconnected to {profile.get('name')} ({profile.get('address')}).")
                return True
            logger.warning(f"Auto-reconnect to {profile.get('address')} failed.")
        except Exception as e:
            logger.error(f"Auto-reconnect exception: {e}")
        return False

    # ------------------------------------------------------------------ #
    # History & settings helpers
    # ------------------------------------------------------------------ #

    def _load_printer_settings(self) -> Dict[str, Any]:
        """Loads density + tear-bar feed settings (configurable per printer)."""
        try:
            settings_file = os.path.join(self.data_dir, "settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    "density": int(data.get("printer", {}).get("density", 8)),
                    "tear_bar_feed_dots": int(data.get("printer", {}).get("tear_bar_feed_dots", 130)),
                }
        except Exception as e:
            logger.warning(f"Failed to load printer settings: {e}")
        return {"density": 8, "tear_bar_feed_dots": 130}

    def generate_test_print_request(self) -> PrintRequest:
        """
        Generates comprehensive hardware diagnostic print page.
        """
        blocks = [
            ContentBlock(type="text", content="MINI PRINT STUDIO", font_size="title", bold=True, align="center", invert=True),
            ContentBlock(type="text", content="HARDWARE DIAGNOSTIC PAGE", font_size="small", align="center"),
            ContentBlock(type="line", line_style="solid"),
            ContentBlock(type="text", content="FONT & SIZE TESTS:", font_size="normal", bold=True, align="left"),
            ContentBlock(type="text", content="Small Font: abcdefghijklmnopqrstuvwxyz\nNormal Font: ABCDEFGHIJKLMNOPQRSTUVWXYZ\nLarge Font: 0123456789", font_size="small", align="left"),
            ContentBlock(type="line", line_style="dashed"),
            ContentBlock(type="text", content="ALIGNMENT TEST:", font_size="normal", bold=True, align="left"),
            ContentBlock(type="text", content="[LEFT ALIGNED]", font_size="small", align="left"),
            ContentBlock(type="text", content="[CENTERED ALIGNED]", font_size="small", align="center"),
            ContentBlock(type="text", content="[RIGHT ALIGNED]", font_size="small", align="right"),
            ContentBlock(type="line", line_style="solid"),
            ContentBlock(type="text", content="THERMAL DENSITY TEST:", font_size="normal", bold=True, align="left"),
            ContentBlock(type="text", content="████████████████████\n▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓\n▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒\n░░░░░░░░░░░░░░░░░░░░", font_size="normal", align="center"),
            ContentBlock(type="line", line_style="dotted"),
            ContentBlock(type="text", content="QR CODE TEST:", font_size="normal", bold=True, align="left"),
            ContentBlock(type="qr", qr_payload="https://miniprint.studio/test", qr_size=4, align="center"),
            ContentBlock(type="text", content="BARCODE TEST:", font_size="normal", bold=True, align="left"),
            ContentBlock(type="barcode", barcode_payload="TEST-998877", barcode_type="code128", barcode_height=35, align="center"),
            ContentBlock(type="line", line_style="double"),
            ContentBlock(type="text", content=f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nStatus: PASS", font_size="small", align="center"),
            ContentBlock(type="space", space_height=16)
        ]
        return PrintRequest(title="Hardware Test Print", blocks=blocks, feed_lines=3, cut_paper=True)

    def save_job_history(self, record: PrintJobRecord):
        history = self.get_job_history()
        record_dict = record.model_dump()
        # Preview PNGs are large base64 blobs; keep them only for the most
        # recent jobs so history.json does not bloat to megabytes.
        if len(history) >= 5:
            record_dict["preview_url"] = None
        history.insert(0, record_dict)
        # Retain last 50 jobs
        history = history[:50]
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save job history: {e}")

    def get_job_history(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def clear_job_history(self):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception as e:
            logger.error(f"Failed to clear job history: {e}")
