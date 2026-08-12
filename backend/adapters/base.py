from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BasePrinterAdapter(ABC):
    """
    Abstract interface for printer hardware adapters.
    """

    def __init__(self, address: str, protocol: str = "escpos"):
        self.address = address
        self.protocol = protocol
        self.connected = False

    @abstractmethod
    async def scan(self) -> List[Dict[str, Any]]:
        """Scans for available devices."""
        pass

    @abstractmethod
    async def connect(self) -> bool:
        """Establishes connection to the printer."""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Closes connection to the printer."""
        pass

    @abstractmethod
    async def send_bytes(self, data: bytes) -> bool:
        """Sends raw protocol binary data to printer."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Checks current connection status."""
        return self.connected

    def get_device_info(self) -> Dict[str, Any]:
        """Optional model/firmware info; adapters without support return {}."""
        return {}

    def get_trace(self) -> List[Dict[str, Any]]:
        """Optional raw wire activity trace; adapters without support return []."""
        return []
