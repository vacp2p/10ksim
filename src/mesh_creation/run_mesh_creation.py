# Python Imports
import argparse
import logging
from pathlib import Path

# Project Imports
import src.logger.logger
from src.mesh_creation.protocols.waku_protocol import WakuProtocol
from topology_creation import TopologyManager

logger = logging.getLogger(__name__)


def create_mesh(yaml_files: list, topology_config: str, kube_config: str, namespace: str, port: int = 8645):
    try:
        manager = TopologyManager(
            kube_config=kube_config,
            namespace=namespace,
            # TODO add protocol to config
            protocol=WakuProtocol(port=port)
        )

        logger.info(f"Deploying nodes from {yaml_files}")
        manager.setup_nodes(yaml_files)

        logger.info(f"Loading topology configuration from {topology_config}")
        config = manager.read_config(topology_config)

        if not config.get("topology_type"):
            raise ValueError("Topology type not specified in config file")

        logger.info(f"Generating {config['topology_type']} topology")
        graph = manager.generate_topology(
            config["topology_type"],
            **config.get("parameters", {})
        )

        logger.info("Configuring node connections")
        manager.configure_node_connections(graph)

        logger.info("Mesh network creation completed successfully")

    except Exception as e:
        logger.error(f"Failed to create mesh network: {str(e)}")
        raise


def main():
    parser = argparse.ArgumentParser(description="Create a mesh network topology")
    parser.add_argument(
        "--yamls",
        nargs="+",
        default=["nodes.yaml"],
        help="Paths to StatefulSet YAML files"
    )
    parser.add_argument(
        "--topology",
        default="topology_config.yaml",
        help="Path to topology configuration YAML"
    )
    parser.add_argument(
        "--kube-config",
        default="yourconfig.yaml",
        help="Path to kubernetes config file"
    )
    parser.add_argument(
        "--namespace",
        default="yournamespace",
        help="Kubernetes namespace"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8645,
        help="Port number for the node protocol"
    )

    args = parser.parse_args()

    for yaml_file in args.yamls:
        if not Path(yaml_file).exists():
            parser.error(f"YAML file not found: {yaml_file}")

    if not Path(args.topology).exists():
        parser.error(f"Topology config file not found: {args.topology}")

    if not Path(args.kube_config).exists():
        parser.error(f"Kubernetes config file not found: {args.kube_config}")

    create_mesh(
        yaml_files=args.yamls,
        topology_config=args.topology,
        kube_config=args.kube_config,
        namespace=args.namespace,
        # TODO move ports to protocol config
        port=args.port
    )


if __name__ == "__main__":
    main()
