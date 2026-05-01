"""
Abstract base driver defining the interface for all automation drivers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger


class AbstractBaseDriver(ABC):
    driver_type: str = "base"

    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config
        self.logger = HarnessLogger(f"driver.{self.driver_type}")
        self._connected = False
        self._screenshots: List[str] = []

    @abstractmethod
    async def launch(self, **kwargs):
        ...

    @abstractmethod
    async def close(self):
        ...

    @abstractmethod
    async def screenshot(self, name: Optional[str] = None) -> str:
        ...

    @property
    def screenshots(self) -> List[str]:
        return self._screenshots

    @property
    def is_connected(self) -> bool:
        return self._connected
