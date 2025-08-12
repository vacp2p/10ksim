# Python imports
import pytest
from unittest.mock import Mock
from pathlib import Path

# Project imports
from src.mesh_creation.protocols.base_protocol import BaseProtocol

@pytest.fixture(autouse=True)
def mock_kubernetes():
    """Mock kubernetes configuration and clients for all tests"""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr('kubernetes.config.load_kube_config', Mock())
        mp.setattr('kubernetes.client.CoreV1Api', Mock)
        mp.setattr('kubernetes.client.AppsV1Api', Mock)
        yield

@pytest.fixture
def test_data_dir():
    """Return a Path object for the test data directory"""
    return Path(__file__).parent / 'data'

@pytest.fixture
def mock_statefulset_yaml():
    """Return a mock StatefulSet YAML configuration"""
    return {
        "kind": "StatefulSet",
        "metadata": {
            "name": "test-statefulset"
        },
        "spec": {
            "replicas": 3,
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "test-container"
                        }
                    ]
                }
            }
        }
    }

@pytest.fixture
def mock_protocol():
    """Create a mock protocol that implements BaseProtocol"""
    protocol = Mock(spec=BaseProtocol)
    protocol.get_node_identifier.return_value = ["curl", "-s", "http://localhost:8645/enr"]
    protocol.get_connection_command.return_value = ["curl", "-s", "-X", "POST", "http://localhost:8645/connect"]
    protocol.parse_identifier_response.return_value = "enr:-123abc"
    return protocol 