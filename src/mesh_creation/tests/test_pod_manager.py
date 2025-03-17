# Python imports
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from kubernetes import client
from result import Ok, Err

# Project imports
from src.mesh_creation.pod_manager import PodManager
from src.mesh_creation.protocols.base_protocol import BaseProtocol

@pytest.fixture
def mock_protocol():
    protocol = Mock(spec=BaseProtocol)
    protocol.get_node_identifier.return_value = Ok(["curl", "-s", "http://localhost:8645/enr"])
    protocol.get_connection_command.return_value = Ok(["curl", "-s", "-X", "POST", "http://localhost:8645/connect"])
    protocol.parse_identifier_response.return_value = Ok("enr:-123abc")
    return protocol

@pytest.fixture
def pod_manager(mock_protocol):
    with patch('kubernetes.config.load_kube_config'):
        with patch('kubernetes.client.CoreV1Api'):
            with patch('kubernetes.client.AppsV1Api'):
                return PodManager(
                    kube_config="test_config.yaml",
                    namespace="test",
                    protocol=mock_protocol
                )

def test_init(pod_manager):
    assert pod_manager.namespace == "test"
    assert pod_manager.deployed_pods == {}

def test_execute_pod_command_success(pod_manager):
    mock_stream = Mock(return_value="test response")
    with patch('kubernetes.stream.stream', mock_stream):
        result = pod_manager.execute_pod_command(
            "test-pod",
            ["echo", "hello"],
            "test-container"
        )
        assert result.is_ok()
        assert result.ok_value == "test response"

def test_execute_pod_command_failure(pod_manager):
    with patch('kubernetes.stream.stream', side_effect=Exception("Connection failed")):
        result = pod_manager.execute_pod_command(
            "test-pod",
            ["echo", "hello"],
            "test-container"
        )
        assert result.is_err()
        assert "Failed to execute command" in result.err_value

def test_execute_pod_command_curl(pod_manager):
    mock_stream = Mock(return_value='Progress... {"key": "value"}')
    with patch('kubernetes.stream.stream', mock_stream):
        result = pod_manager.execute_pod_command(
            "test-pod",
            ["curl", "http://test"],
            "test-container"
        )
        assert result.is_ok()
        assert result.ok_value == '{"key": "value"}'

def test_get_pod_identifier_success(pod_manager, mock_protocol):
    with patch.object(pod_manager, 'execute_pod_command', return_value=Ok("test response")):
        result = pod_manager.get_pod_identifier("test-pod", "test-container")
        assert result.is_ok()
        assert result.ok_value == "enr:-123abc"

def test_get_pod_identifier_failure(pod_manager, mock_protocol):
    with patch.object(pod_manager, 'execute_pod_command', return_value=Err("Command failed")):
        result = pod_manager.get_pod_identifier("test-pod", "test-container")
        assert result.is_err()
        assert "Failed to get pod identifier" in result.err_value

def test_connect_pods_success(pod_manager):
    source_pod = {"name": "pod1", "identifier": "id1"}
    target_pod = {"name": "pod2", "identifier": "id2"}
    pod_manager.deployed_pods = {'container_name': 'test-container'}
    
    with patch.object(pod_manager, 'execute_pod_command', return_value=Ok("success")):
        result = pod_manager.connect_pods(source_pod, target_pod)
        assert result.is_ok()

def test_connect_pods_failure(pod_manager):
    source_pod = {"name": "pod1", "identifier": "id1"}
    target_pod = {"name": "pod2", "identifier": "id2"}
    pod_manager.deployed_pods = {'container_name': 'test-container'}
    
    with patch.object(pod_manager, 'execute_pod_command', return_value=Err("Connection failed")):
        result = pod_manager.connect_pods(source_pod, target_pod)
        assert result.is_err()
        assert "Failed to connect pods" in result.err_value

def test_apply_yaml_file_success(pod_manager):
    mock_yaml = {
        "kind": "StatefulSet",
        "metadata": {"name": "test-ss"},
        "spec": {
            "replicas": 3,
            "template": {
                "spec": {
                    "containers": [{"name": "test-container"}]
                }
            }
        }
    }
    
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = mock_yaml
        result = pod_manager.apply_yaml_file(Path("test.yaml"))
        assert result.is_ok()
        assert pod_manager.deployed_pods['ss_name'] == "test-ss"
        assert len(pod_manager.deployed_pods['pods']) == 3
        assert pod_manager.deployed_pods['container_name'] == "test-container"

def test_apply_yaml_file_invalid_yaml(pod_manager):
    with patch('builtins.open', create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.side_effect = Exception("Invalid YAML")
        result = pod_manager.apply_yaml_file(Path("test.yaml"))
        assert result.is_err()
        assert "Failed to read YAML file" in result.err_value

def test_wait_for_pods_ready_success(pod_manager):
    pod_manager.deployed_pods = {
        'ss_name': 'test-ss',
        'container_name': 'test-container',
        'pods': [{'name': 'test-ss-0', 'identifier': ''}]
    }
    
    mock_ss = Mock()
    mock_ss.status.ready_replicas = 1
    mock_ss.spec.replicas = 1
    mock_ss.spec.selector.match_labels = {"app": "test"}
    
    mock_pod = Mock()
    mock_pod.metadata.name = "test-ss-0"
    
    mock_pod_list = Mock()
    mock_pod_list.items = [mock_pod]
    
    with patch.object(pod_manager.apps_api, 'read_namespaced_stateful_set', return_value=mock_ss):
        with patch.object(pod_manager.api, 'list_namespaced_pod', return_value=mock_pod_list):
            with patch.object(pod_manager, 'get_pod_identifier', return_value=Ok("test-id")):
                result = pod_manager.wait_for_pods_ready()
                assert result.is_ok()
                assert pod_manager.deployed_pods['pods'][0]['identifier'] == "test-id"

def test_wait_for_pods_ready_timeout(pod_manager):
    pod_manager.deployed_pods = {
        'ss_name': 'test-ss',
        'container_name': 'test-container',
        'pods': [{'name': 'test-ss-0', 'identifier': ''}]
    }
    
    mock_ss = Mock()
    mock_ss.status.ready_replicas = 0
    mock_ss.spec.replicas = 1
    
    with patch.object(pod_manager.apps_api, 'read_namespaced_stateful_set', return_value=mock_ss):
        result = pod_manager.wait_for_pods_ready(timeout=1)
        assert result.is_err()
        assert "Timeout waiting for pods" in result.err_value

def test_configure_connections_success(pod_manager):
    pod_manager.deployed_pods = {
        'pods': [
            {'name': 'test-ss-0', 'identifier': 'id0'},
            {'name': 'test-ss-1', 'identifier': 'id1'}
        ],
        'container_name': 'test-container'
    }
    
    mock_graph = Mock()
    mock_graph.edges.return_value = [(0, 1)]
    
    node_to_pod = {0: 'test-ss-0', 1: 'test-ss-1'}
    
    with patch.object(pod_manager, 'connect_pods', return_value=Ok(None)):
        result = pod_manager.configure_connections(node_to_pod, mock_graph)
        assert result.is_ok() 