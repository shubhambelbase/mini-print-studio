import asyncio
import socket
import logging
from typing import List, Dict, Any, Optional
from backend.adapters.base import BasePrinterAdapter

logger = logging.getLogger("BluetoothClassicAdapter")


class BluetoothClassicAdapter(BasePrinterAdapter):
    """
    Bluetooth Classic (SPP/RFCOMM socket or COM serial port) adapter.
    """

    def __init__(self, address: str, protocol: str = "escpos", channel: int = 1):
        super().__init__(address, protocol)
        self.channel = channel
        self.sock: Optional[socket.socket] = None

    async def scan(self) -> List[Dict[str, Any]]:
        # Scanning Bluetooth Classic on Windows via socket is not natively supported without PyBluez or OS API.
        return []

    async def connect(self) -> bool:
        loop = asyncio.get_running_loop()
        try:
            # Check if address is a COM port (e.g. COM3) or MAC address
            if self.address.upper().startswith("COM"):
                import serial
                self.sock = serial.Serial(self.address, 9600, timeout=5)
                self.connected = True
                return True
            else:
                # Attempt RFCOMM socket connection (AF_BLUETOOTH if supported by OS Python)
                if hasattr(socket, "AF_BLUETOOTH"):
                    def _do_connect():
                        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                        s.connect((self.address, self.channel))
                        return s
                    self.sock = await loop.run_in_executor(None, _do_connect)
                    self.connected = True
                    return True
                else:
                    logger.warning("AF_BLUETOOTH is not supported on this Python build.")
                    return False
        except Exception as e:
            logger.error(f"Failed to connect via Bluetooth Classic: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> bool:
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error closing socket: {e}")
        self.sock = None
        self.connected = False
        return True

    async def send_bytes(self, data: bytes) -> bool:
        if not self.connected or not self.sock:
            raise ConnectionError("Bluetooth Classic printer is not connected.")

        loop = asyncio.get_running_loop()
        if hasattr(self.sock, "write"):  # Serial port
            await loop.run_in_executor(None, self.sock.write, data)
        else:  # Socket
            await loop.run_in_executor(None, self.sock.sendall, data)
        return True

    def is_connected(self) -> bool:
        return self.connected
