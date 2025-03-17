# Python Imports
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseProtocol(ABC):
    """Abstract base class for node communication protocols."""

    @abstractmethod
    def get_node_identifier(self) -> list:
        pass

    @abstractmethod
    def get_connection_command(self, target_identifier: str) -> list:
        pass

    @abstractmethod
    def parse_identifier_response(self, response: str) -> str:
        pass
