import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from backend.adapters.base import BasePrinterAdapter

logger = logging.getLogger("MockPrinterAdapter")

MOCK_PRINTERS_FILE = os.path.join(
    os.environ.get("MPS_DATA_DIR", "data"),
    "printers.json"
)


class MockPrinterAdapter(BasePrinterAdapter):
    """
    Simulated printer adapter used for offline development and testing.
    Accepts and logs protocol bytes without sending to hardware.
    """

    SEND_DELAY_SECONDS = 0.05

    def __init__(self, address: str = "", protocol: str = "escpos"):
        super().__init__(address, protocol)
        self.last_payload: Optional[bytes] = None

    async def scan(self) -> List[Dict[str, Any]]:
        devices = []
        if os.path.exists(MOCK_PRINTERS_FILE):
            try:
                with open(MOCK_PRINTERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for entry in data:
                    entry.setdefault("protocol", "escpos")
                    entry.setdefault("connection_type", "mock")
                    entry.setdefault("status", "available")
                    devices.append(entry)
            except Exception as e:
                logger.error(f"Failed to load mock printer profiles: {e}")
        if not devices:
            devices = [{
                "id": "mock-printer-01",
                "name": "Virtual Thermal Printer (Simulator)",
                "connection_type": "mock",
                "address": "00:11:22:33:44:55",
                "protocol": "escpos",
                "printable_width_px": 384,
                "paper_width_mm": 58,
                "status": "available",
                "is_default": True
            }]
        return devices

    async def connect(self) -> bool:
        self.connected = True
        logger.info(f"Mock printer connected (protocol={self.protocol}).")
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        return True

    async def send_bytes(self, data: bytes) -> bool:
        if not self.connected:
            raise ConnectionError("Mock printer is not connected.")
        self.last_payload = data
        # Simulate realistic hardware latency so queue ordering is observable.
        await asyncio.sleep(self.SEND_DELAY_SECONDS)
        logger.info(f"Mock printer received {len(data)} bytes (protocol={self.protocol}).")
        return True

    def is_connected(self) -> bool:
        return self.connected
