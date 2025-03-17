# PythonImports
from pathlib import Path
import random
import networkx as nx
import logging
from kubernetes import client, config
from result import Result, Err, Ok

# Project Imports
import src.logger.logger
from typing import Optional

from src.mesh_creation.pod_manager import PodManager
from src.mesh_creation.protocols.base_protocol import BaseProtocol

logger = logging.getLogger(__name__)


class TopologyManager:
    def __init__(self, kube_config: str, namespace: str, protocol: Optional[BaseProtocol]):
        self.namespace = namespace
        self.protocol = protocol
        self.pod_manager = PodManager(kube_config, namespace, protocol=self.protocol)
        config.load_kube_config(config_file=kube_config)
        self.api = client.CoreV1Api()

    def setup_nodes(self, yaml_file: Path) -> Result[None, Err]:
        result = self.pod_manager.apply_yaml_file(yaml_file)
        if result.is_err():
            return result

        result = self.pod_manager.wait_for_pods_ready()
        if result.is_err():
            return result

        return Ok(None)

    def read_pajek(self, pajek_path: str) -> nx.Graph:
        return nx.read_pajek(pajek_path)

    def generate_topology(self, topology_type: str, **params) -> Result[nx.Graph, None]:
        if topology_type == "libp2p_custom":
            return Ok(self.configure_libp2p_custom(**params))
        else:
            logger.error(f"Unsupported topology type: {topology_type}")
            return Err(None)

    def configure_libp2p_custom(self, n: int, d_high: int, d_low: int) -> nx.Graph:
        G = nx.Graph()
        G.add_nodes_from(range(n))

        # Ensure minimum degree by adding edges
        while any(G.degree(node) < d_low for node in G.nodes):
            node = random.choice([n for n in G.nodes if G.degree(n) < d_low])
            possible_neighbors = [n for n in G.nodes if
                                  n != node and not G.has_edge(node, n) and G.degree(n) < d_high]

            # Add edges until node reaches min_degree or no valid neighbors remain
            while G.degree(node) < d_low and possible_neighbors:
                neighbor = random.choice(possible_neighbors)
                G.add_edge(node, neighbor)
                possible_neighbors.remove(neighbor)

        assert all(d_low <= d <= d_high for _, d in G.degree()), "Some nodes do not meet the degree constraints"

        return G

    def configure_node_connections(self, graph: nx.Graph) -> Result[None, None]:
        logger.info("Starting node connection configuration")

        pods = self.pod_manager.deployed_pods['pods']
        if len(pods) < graph.number_of_nodes():
            logger.error(f"Not enough pods ({len(pods)}) for the topology ({graph.number_of_nodes()} nodes)")
            return Err(None)

        node_to_pod = {i: pod['name'] for i, pod in enumerate(pods[:graph.number_of_nodes()])}
        logger.debug(f"Node to pod mapping: {node_to_pod}")
        result = self.pod_manager.configure_connections(node_to_pod, graph)
        if result.is_err():
            return Err(None)

        return Ok(None)
