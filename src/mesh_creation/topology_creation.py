# PythonImports
import networkx as nx
import logging
import yaml
from kubernetes import client, config

# Project Imports
import src.logger.logger
from pod_manager import PodManager
from typing import Dict, Any, Optional, List

from src.mesh_creation.protocols.base_protocol import BaseProtocol

logger = logging.getLogger(__name__)


class TopologyManager:
    def __init__(self, kube_config: str, namespace: str, protocol: Optional[BaseProtocol]):
        self.namespace = namespace
        self.protocol = protocol
        self.pod_manager = PodManager(kube_config, namespace, protocol=self.protocol)
        config.load_kube_config(config_file=kube_config)
        self.api = client.CoreV1Api()

    def setup_nodes(self, yaml_files: List[str]) -> None:
        self.pod_manager.apply_yaml_files(yaml_files)
        if not self.pod_manager.wait_for_pods_ready():
            raise RuntimeError("Failed to deploy nodes")

    def read_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def read_pajek(self, pajek_path: str) -> nx.Graph:
        return nx.read_pajek(pajek_path)

    def generate_topology(self, topology_type: str, **params) -> nx.Graph:
        if topology_type == "random":
            n = params.get("n", 10)
            p = params.get("p", 0.2)
            return nx.erdos_renyi_graph(n, p)
        elif topology_type == "scale_free":
            n = params.get("n", 10)
            m = params.get("m", 2)
            return nx.barabasi_albert_graph(n, m)
        elif topology_type == "small_world":
            n = params.get("n", 10)
            k = params.get("k", 4)
            p = params.get("p", 0.1)
            return nx.watts_strogatz_graph(n, k, p)
        else:
            raise ValueError(f"Unsupported topology type: {topology_type}")

    def configure_node_connections(self, graph: nx.Graph):
        # TODO take into account multi graph connections
        all_pods = self.pod_manager.get_all_pods()

        if len(all_pods) < graph.number_of_nodes():
            raise ValueError(f"Not enough pods ({len(all_pods)}) for the topology ({graph.number_of_nodes()} nodes)")

        node_to_pod = {i: pod for i, pod in enumerate(all_pods[:graph.number_of_nodes()])}

        for node in graph.nodes():
            source_pod = node_to_pod[node]
            neighbors = list(graph.neighbors(node))

            for neighbor in neighbors:
                target_pod = node_to_pod[neighbor]
                self.pod_manager.connect_pods(source_pod, target_pod)
