# Python imports
import pytest
from unittest.mock import Mock
from result import Ok, Err

# Project imports
from src.mesh_creation.protocols.base_protocol import BaseProtocol
from src.mesh_creation.protocols.waku_protocol import WakuProtocol

def test_waku_protocol_init():
    protocol = WakuProtocol(port=8645)
    assert protocol.port == 8645

def test_waku_protocol_get_node_identifier():
    protocol = WakuProtocol(port=8645)
    result = protocol.get_node_identifier()
    assert result.is_ok()
    assert result.ok_value == ["curl", "-s", "http://localhost:8645/enr"]

def test_waku_protocol_get_connection_command():
    protocol = WakuProtocol(port=8645)
    enr = "enr:-123abc"
    result = protocol.get_connection_command(enr)
    assert result.is_ok()
    assert result.ok_value == ["curl", "-s", "-X", "POST", f"http://localhost:8645/connect/{enr}"]

def test_waku_protocol_parse_identifier_response_success():
    protocol = WakuProtocol(port=8645)
    response = '{"enr": "enr:-123abc"}'
    result = protocol.parse_identifier_response(response)
    assert result.is_ok()
    assert result.ok_value == "enr:-123abc"

def test_waku_protocol_parse_identifier_response_invalid():
    protocol = WakuProtocol(port=8645)
    response = 'invalid json'
    result = protocol.parse_identifier_response(response)
    assert result.is_err()
    assert "Failed to parse JSON response" in result.err_value

def test_base_protocol_abstract_methods():
    class ConcreteProtocol(BaseProtocol):
        def get_node_identifier(self):
            return Ok(["test"])
        
        def get_connection_command(self, identifier):
            return Ok(["test", identifier])
        
        def parse_identifier_response(self, response):
            return Ok(response)

    protocol = ConcreteProtocol()
    assert protocol.get_node_identifier().ok_value == ["test"]
    assert protocol.get_connection_command("id").ok_value == ["test", "id"]
    assert protocol.parse_identifier_response("response").ok_value == "response" 