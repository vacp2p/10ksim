# Python imports
import pytest
from unittest.mock import Mock, patch
import networkx as nx
from pathlib import Path
from result import Ok, Err

# Project imports
from src.mesh_creation.topology_creation import TopologyManager
from src.mesh_creation.protocols.base_protocol import BaseProtocol

@pytest.fixture
def mock_protocol():
    return Mock(spec=BaseProtocol)

@pytest.fixture
def topology_manager(mock_protocol):
    with patch('kubernetes.config.load_kube_config'):
        with patch('kubernetes.client.CoreV1Api'):
            return TopologyManager(
                kube_config="test_config.yaml",
                namespace="test",
                protocol=mock_protocol
            )

def test_init(topology_manager, mock_protocol):
    assert topology_manager.namespace == "test"
    assert topology_manager.protocol == mock_protocol

def test_setup_nodes_success(topology_manager):
    with patch.object(topology_manager.pod_manager, 'apply_yaml_file', return_value=Ok(None)):
        with patch.object(topology_manager.pod_manager, 'wait_for_pods_ready', return_value=Ok(None)):
            result = topology_manager.setup_nodes(Path("test.yaml"))
            assert result.is_ok()

def test_setup_nodes_failure(topology_manager):
    with patch.object(topology_manager.pod_manager, 'apply_yaml_file', return_value=Ok(None)):
        with patch.object(topology_manager.pod_manager, 'wait_for_pods_ready', return_value=Err("Failed to wait for pods")):
            result = topology_manager.setup_nodes(Path("test.yaml"))
            assert result.is_err()
            assert "Failed to wait for pods" in result.err_value

def test_generate_topology_libp2p_custom(topology_manager):
    result = topology_manager.generate_topology(
        "libp2p_custom",
        n=5,
        d_low=2,
        d_high=4
    )
    assert result.is_ok()
    graph = result.ok_value
    assert isinstance(graph, nx.Graph)
    assert len(graph.nodes) == 5
    assert all(2 <= d <= 4 for _, d in graph.degree())

def test_generate_topology_invalid_type(topology_manager):
    result = topology_manager.generate_topology("invalid_type")
    assert result.is_err()

def test_configure_libp2p_custom(topology_manager):
    graph = topology_manager.configure_libp2p_custom(n=5, d_high=4, d_low=2)
    assert isinstance(graph, nx.Graph)
    assert len(graph.nodes) == 5
    assert all(2 <= d <= 4 for _, d in graph.degree())

def test_configure_node_connections_success(topology_manager):
    mock_graph = nx.Graph()
    mock_graph.add_edges_from([(0, 1), (1, 2)])
    
    topology_manager.pod_manager.deployed_pods = {
        'pods': [
            {'name': 'test-0', 'identifier': 'id0'},
            {'name': 'test-1', 'identifier': 'id1'},
            {'name': 'test-2', 'identifier': 'id2'}
        ]
    }
    
    with patch.object(topology_manager.pod_manager, 'configure_connections', return_value=Ok(None)):
        result = topology_manager.configure_node_connections(mock_graph)
        assert result.is_ok()

def test_configure_node_connections_not_enough_pods(topology_manager):
    mock_graph = nx.Graph()
    mock_graph.add_edges_from([(0, 1), (1, 2)])
    
    topology_manager.pod_manager.deployed_pods = {
        'pods': [
            {'name': 'test-0', 'identifier': 'id0'},
            {'name': 'test-1', 'identifier': 'id1'}
        ]
    }
    
    result = topology_manager.configure_node_connections(mock_graph)
    assert result.is_err()
