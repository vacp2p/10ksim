# Python Imports
import ast
import json
import logging

# Project Imports
from src.mesh_creation.protocols.base_protocol import BaseProtocol

logger = logging.getLogger(__name__)


class WakuProtocol(BaseProtocol):
    
    def __init__(self, port: int = 8645):
        self.port = port
        
    def get_node_identifier(self) -> list:
        return [
            "curl", "-s", "-X", "GET",
            f"http://127.0.0.1:{self.port}/debug/v1/info",
            "-H", "accept: application/json"
        ]
        
    def get_connection_command(self, target_identifier: str) -> list:
        return [
            "curl", "-s", "-X", "POST",
            f"http://127.0.0.1:{self.port}/admin/v1/peers",
            "-H", "Content-Type: application/json",
            "-d", f"[{json.dumps(target_identifier)}]"
        ]
        
    def parse_identifier_response(self, response: str) -> str:
        try:
            try:
                data = ast.literal_eval(response)
            except (ValueError, SyntaxError) as e:
                response_json = response.replace("'", '"')
                data = json.loads(response_json)
            
            return data["listenAddresses"][0]
        except Exception as e:
            logger.error(f"Error parsing Waku node identifier: {str(e)}")
            logger.error(f"Failed response content: {response}")
            return ""
