# Python Imports

# Project Imports
from src.mesh_creation.protocols.base_protocol import BaseProtocol


class LibP2PProtocol(BaseProtocol):

    def __init__(self, port: int = 8080):
        self.port = port

    def get_node_identifier(self) -> list:
        pass

    def get_connection_command(self, target_identifier: str) -> list:
        pass

    def parse_identifier_response(self, response: str) -> str:
        pass