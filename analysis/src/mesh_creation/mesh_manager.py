# Python Imports
import logging
import yaml
from pathlib import Path
from typing import List, Dict, Any, Tuple

from result import Result, Err, Ok

# Project Imports
import src.logger.logger
from topology_creation import TopologyManager
from protocols.base_protocol import BaseProtocol

logger = logging.getLogger("src.mesh_creation.mesh_manager")

class MeshManager:
    def __init__(self, kube_config: str, namespace: str):
        self.kube_config = kube_config
        self.namespace = namespace
        
    def create_mesh(self, statefulset_configs: List[Tuple[str, Dict[str, Any], BaseProtocol]]) -> None:
        """
        Create a mesh network using the provided StatefulSets and their respective topology configurations
        and protocols.
        
        Args:
            statefulset_configs: List of tuples (statefulset_yaml_path, topology_config, protocol)
                where:
                - statefulset_yaml_path: path to the StatefulSet YAML file
                - topology_config: dictionary containing:
                    - type: implemented topology type (e.g., "custom", "random", etc.)
                    - parameters: dictionary of parameters for the topology
                - protocol: protocol implementation for this StatefulSet
                
        Example:
            configs = [
                ("statefulset1.yaml", {
                    "type": "libp2p_custom",
                    "parameters": {"n": 5, "d_low": 4, "d_high": 8}
                }, WakuProtocol(port=8645)),
                ("statefulset2.yaml", {
                    "type": "random",
                    "parameters": {"n": 3, "p": 0.5}
                }, LibP2PProtocol(port=8080))
            ]
        """

        topology_managers = {
            yaml_file: TopologyManager(
                kube_config=self.kube_config,
                namespace=self.namespace,
                protocol=protocol
            )
            for yaml_file, _, protocol in statefulset_configs
        }

        yaml_files = [config[0] for config in statefulset_configs]
        for yaml_file in yaml_files:
            logger.info(f"Deploying nodes from {yaml_file}")
            topology_managers[yaml_file].setup_nodes(Path(yaml_file))

        for yaml_file, topology_config, _ in statefulset_configs:
            logger.info(f"Generating {topology_config['type']} topology for {yaml_file}")
            topology_manager = topology_managers[yaml_file]

            result = topology_manager.generate_topology(
                topology_config["type"],
                **topology_config.get("parameters", {})
            )
            if result.is_err():
                break

            result = topology_manager.configure_node_connections(result.ok_value)
            if result.is_err():
                break

    def create_mesh_from_pajek_files(self, statefulset_configs: List[Tuple[str, str, BaseProtocol]]) -> None:
        """
        Create a mesh network using Pajek format topology files.
        
        Args:
            statefulset_configs: List of tuples (statefulset_yaml_path, pajek_file_path, protocol)
        """
        try:
            # Create topology managers for each StatefulSet with its protocol
            topology_managers = {
                yaml_file: TopologyManager(
                    kube_config=self.kube_config,
                    namespace=self.namespace,
                    protocol=protocol
                )
                for yaml_file, _, protocol in statefulset_configs
            }
            
            # Deploy all nodes first
            yaml_files = [config[0] for config in statefulset_configs]
            logger.info(f"Deploying nodes from {yaml_files}")
            
            # Deploy nodes for each StatefulSet using its specific topology manager
            for yaml_file in yaml_files:
                topology_managers[yaml_file].setup_nodes([yaml_file])
            
            # Configure topology for each StatefulSet
            for yaml_file, pajek_path, _ in statefulset_configs:
                logger.info(f"Loading topology from {pajek_path} for {yaml_file}")
                topology_manager = topology_managers[yaml_file]
                
                graph = topology_manager.read_pajek(pajek_path)
                
                # Configure the connections for this StatefulSet
                logger.info(f"Configuring node connections for {yaml_file}")
                topology_manager.configure_node_connections(graph)
            
            logger.info("Mesh network creation completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to create mesh network from Pajek files: {str(e)}")
            raise
            
    def _create_protocol_instance(self, protocol_type: str, **params) -> Result[BaseProtocol, str]:
        """Create a protocol instance based on type and parameters."""
        from protocols.waku_protocol import WakuProtocol
        from protocols.libp2p_protocol import LibP2PProtocol
        
        protocol_classes = {
            "waku": WakuProtocol,
            "libp2p": LibP2PProtocol
        }
        
        if protocol_type not in protocol_classes:
            return Err(f"Unsupported protocol type: {protocol_type}")
            
        return Ok(protocol_classes[protocol_type](**params))
