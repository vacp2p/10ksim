import argparse
import asyncio
import logging
import os
import sys
from argparse import Namespace
from contextlib import ExitStack
from pathlib import Path
from typing import Dict, Optional

# Add deployments directory to path
_SCRIPT_DIR = Path(__file__).resolve().parent
_DEPLOYMENTS_DIR = _SCRIPT_DIR.parent.parent
if str(_DEPLOYMENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOYMENTS_DIR))

from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt

from core.configs.statefulset import StatefulSetConfig
from core.kube_utils import get_YAML
from experiments.base_experiment import BaseExperiment
from registry import experiment

from libp2p.builders import (
    Libp2pStatefulSetBuilder,
    Publisher,
    PublisherConfig,
    create_mix_pvc,
)
from libp2p.builders.nodes import Nodes

logger = logging.getLogger(__name__)


DEFAULTS = {
    "namespace": "zerotesting-nimlibp2p",
    "servicename": "nimp2p-service",
    "statefulset_name": "pod",
    "peers": 100,
    "muxer": "yamux",
    "image": "ufarooqstatus/refactored-test-node:v1.0",
    "publisher_image": "ufarooqstatus/libp2p-publisher:v1.0",
    "delay_ms": 100,
    "jitter_ms": 30,
    "output_dir": "./regression",
    # mix protocol defaults
    "num_mix": 50,
    "mix_d": 3,
    #test node defaults
    "connect_to": 10,
    "fragments": 1,
    "shadow_env": False,
}


# Deployment builders
def build_nodes(
    namespace: str,
    servicename: str,
    statefulset_name: str,
    num_nodes: int,
    peers: Optional[int] = None,
    connect_to: int = 10,
    muxer: str = "yamux",
    fragments: int = 1,
    shadow_env: bool = False,
    node_image: Optional[str] = None,
    # vaclab-v1: if delay applied
    network_delay_ms: Optional[int] = None,
    network_jitter_ms: int = 30,
    # mix protocol: if with_mix is set
    with_mix: bool = False,
    num_mix: int = 50,
    mix_d: int = 3,
    # vaclab-v2: OVN options (if ovn_ingress_mbps is set)
    ovn_ingress_mbps: Optional[int] = None,
    ovn_egress_mbps: Optional[int] = None,
    ovn_logical_switch: Optional[str] = None,
) -> Dict[str, dict]:
    """
    Build libp2p StatefulSet specification.
    network_delay, mix protocol, OVN are optional
    """
    api_client = client.ApiClient()
    
    def to_dict(deployment) -> dict:
        return api_client.sanitize_for_serialization(deployment)
    
    if peers is None:
        peers = num_nodes
    
    result = {}
    
    # Create PVC if mix protocol is enabled
    if with_mix:
        pvc = create_mix_pvc(namespace=namespace)
        result["pvc"] = to_dict(pvc)
    
    # Build StatefulSet
    builder = Libp2pStatefulSetBuilder(config=StatefulSetConfig())
    builder.with_libp2p_config(
        name=statefulset_name,
        namespace=namespace,
        num_nodes=num_nodes,
        peers=peers,
        connect_to=connect_to,
        muxer=muxer,
        service=servicename,
        fragments=fragments,
        shadow_env=shadow_env,
        image=node_image,
    )
    
    # Add network delay if specified
    if network_delay_ms is not None:
        builder.with_network_delay(
            delay_ms=network_delay_ms,
            jitter_ms=network_jitter_ms,
        )
    
    # Add mix protocol if enabled
    if with_mix:
        builder.with_mix(
            num_mix=num_mix,
            mix_d=mix_d,
        )
    
    # Add OVN bandwidth shaping if specified (TODO)
    if ovn_ingress_mbps is not None:
        egress = ovn_egress_mbps if ovn_egress_mbps is not None else ovn_ingress_mbps
        builder.with_ovn_bandwidth(
            ingress_mbps=ovn_ingress_mbps,
            egress_mbps=egress,
        )
        if ovn_logical_switch is not None:
            builder.with_ovn_logical_switch(ovn_logical_switch)
    
    nodes = builder.build()
    result["nodes"] = to_dict(nodes)
    
    return result


def build_publisher(
    namespace: str,
    servicename: str,
    messages: int = 20,
    msg_size_bytes: int = 100,
    delay_seconds: int = 3,
    network_size: int = 50,
    peer_selection: str = "service",
    publisher_image: Optional[str] = None,
) -> dict:
    """
    Build publisher pod specification.
    """
    config = PublisherConfig(
        messages=messages,
        msg_size_bytes=msg_size_bytes,
        delay_seconds=delay_seconds,
        network_size=network_size,
        peer_selection=peer_selection,
    )
    
    return Publisher.create_pod_spec(
        config=config,
        namespace=namespace,
        service_name=servicename,
        image=publisher_image,
    )


# For framework deployment (deployment.py)
@experiment(name="libp2p-experiment")
class Libp2pExperiment(BaseExperiment, BaseModel):
    """
    libp2p test node deployments:
    - Build deployments with/without mix
    - Optional Network delay
    - OVN latency/bandwidth shaping (TODO)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, 
            help="libp2p experiment"
        )
        BaseExperiment.add_args(subparser)
        
        # Add libp2p-specific arguments
        subparser.add_argument(
            "--num-nodes",
            type=int,
            help=f"Number of peers/replicas (default: {DEFAULTS['peers']})",
        )
        subparser.add_argument(
            "--servicename",
            type=str,
            help=f"Service name for DNS resolution (default: {DEFAULTS['servicename']})",
        )
        subparser.add_argument(
            "--statefulset-name",
            type=str,
            help=f"StatefulSet name (default: {DEFAULTS['statefulset_name']})",
        )
        subparser.add_argument(
            "--use-mix",
            help="Enable mix protocol",
        )
        subparser.add_argument(
            "--network-delay-ms",
            type=int,
            help="Network delay in milliseconds (optional)",
        )
        subparser.add_argument(
            "--node-image",
            type=str,
            help=f"Custom node image (default: {DEFAULTS['image']})",
        )
        subparser.add_argument(
            "--publisher-image",
            type=str,
            help=f"Custom publisher image (default: {DEFAULTS['publisher_image']})",
        )
        subparser.add_argument(
            "--ovn-bandwidth-mbps",
            type=int,
            help="OVN bandwidth limit in Mbps (optional)",
        )

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    class ExpConfig(BaseModel):
        model_config = ConfigDict(extra="ignore")

        num_messages: NonNegativeInt = 20
        delay_cold_start: NonNegativeFloat = 5
        delay_after_publish: NonNegativeFloat = 0.5
        msg_size_bytes: NonNegativeInt = 100

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[dict],
        stack: ExitStack,
    ):
        self.log_event("run_start")

        if values_yaml is None:
            values_yaml = {}
        config = self.ExpConfig(**values_yaml)
        
        servicename = getattr(args, 'servicename', DEFAULTS["servicename"])
        statefulset_name = getattr(args, 'statefulset_name', DEFAULTS["statefulset_name"])

        # Build deployments with unified function
        deployments = build_nodes(
            namespace=args.namespace,
            servicename=servicename,
            statefulset_name=statefulset_name,
            num_nodes=args.num_nodes,
            node_image=args.node_image,
            network_delay_ms=args.network_delay_ms,
            with_mix=args.use_mix,
            ovn_ingress_mbps=args.ovn_bandwidth_mbps,
        )

        # Deploy PVC first if using mix
        if "pvc" in deployments:
            pvc = deployments["pvc"]
            name = pvc["metadata"]["name"]
            out_path = Path(workdir) / name / f"{name}.yaml"
            os.makedirs(out_path.parent, exist_ok=True)
            logger.info(f"Dumping PVC `{name}` to `{out_path}`")
            with open(out_path, "w") as out_file:
                yaml = get_YAML()
                yaml.dump(pvc, out_file)
            await self.deploy(api_client, stack, args, values_yaml, deployment=pvc)

        # Deploy nodes
        nodes = deployments["nodes"]
        name = nodes["metadata"]["name"]
        out_path = Path(workdir) / name / f"{name}.yaml"
        os.makedirs(out_path.parent, exist_ok=True)
        logger.info(f"Dumping deployment `{name}` to `{out_path}`")
        with open(out_path, "w") as out_file:
            yaml = get_YAML()
            yaml.dump(nodes, out_file)
        await self.deploy(api_client, stack, args, values_yaml, deployment=nodes)

        # Wait for nodes to be ready
        await asyncio.sleep(config.delay_cold_start)

        # Deploy publisher
        publisher = build_publisher(
            namespace=args.namespace,
            servicename=servicename,
            messages=config.num_messages,
            msg_size_bytes=config.msg_size_bytes,
            network_size=args.num_nodes,
            publisher_image=args.publisher_image,
        )
        
        pub_path = Path(workdir) / "publisher" / "publisher.yaml"
        os.makedirs(pub_path.parent, exist_ok=True)
        logger.info(f"Dumping publisher to `{pub_path}`")
        with open(pub_path, "w") as out_file:
            yaml = get_YAML()
            yaml.dump(publisher, out_file)
        await self.deploy(
            api_client, stack, args, values_yaml, 
            deployment=publisher, 
            wait_for_ready=False
        )

        self.log_event("publisher_started")

        # Wait for experiment to complete
        wait_time = config.num_messages * (config.delay_after_publish + 1) + 30
        logger.info(f"Waiting {wait_time}s for experiment to complete")
        await asyncio.sleep(wait_time)

        self.log_event("internal_run_finished")


def generate_yamls(
    output_dir: str,
    namespace: str,
    servicename: str,
    statefulset_name: str,
    peers: int,
    muxer: str,
    node_image: str,
    publisher_image: str,
    with_delay: bool = False,
    delay_ms: int = 100,
    jitter_ms: int = 30,
    with_mix: bool = False,
    num_mix: int = 50,
    mix_d: int = 3,
):

    os.makedirs(output_dir, exist_ok=True)
    yaml = get_YAML()
    
    deployments = build_nodes(
        namespace=namespace,
        servicename=servicename,
        statefulset_name=statefulset_name,
        num_nodes=peers,
        muxer=muxer,
        node_image=node_image,
        network_delay_ms=delay_ms if with_delay else None,
        network_jitter_ms=jitter_ms,
        with_mix=with_mix,
        num_mix=num_mix,
        mix_d=mix_d,
    )
    
    # Write PVC if mix is enabled
    if "pvc" in deployments:
        pvc_path = os.path.join(output_dir, "mixpvc.yaml")
        with open(pvc_path, "w") as f:
            yaml.dump(deployments["pvc"], f)
        print(f"  Generated: {pvc_path}")
    
    # Write test nodes deployment
    nodes_path = os.path.join(output_dir, "nodes.yaml")
    with open(nodes_path, "w") as f:
        yaml.dump(deployments["nodes"], f)
    print(f"  Generated: {nodes_path}")

    # Write publisher
    publisher = build_publisher(
        namespace=namespace,
        servicename=servicename,
        network_size=peers,
        publisher_image=publisher_image,
    )
    publisher_path = os.path.join(output_dir, "publisher.yaml")
    with open(publisher_path, "w") as f:
        yaml.dump(publisher, f)
    print(f"  Generated: {publisher_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Kubernetes YAML files for libp2p deployments"
    )
    
    parser.add_argument(
        "--namespace",
        type=str,
        help=f"Kubernetes namespace (default: {DEFAULTS['namespace']})",
    )
    parser.add_argument(
        "--servicename",
        type=str,
        help=f"Service name for DNS resolution (default: {DEFAULTS['servicename']})",
    )
    parser.add_argument(
        "--statefulset-name",
        type=str,
        help=f"StatefulSet name (default: {DEFAULTS['statefulset_name']})",
    )
    parser.add_argument(
        "--peers",
        type=int,
        help=f"Number of peers/replicas (default: {DEFAULTS['peers']})",
    )
    parser.add_argument(
        "--muxer",
        type=str,
        choices=["mplex", "yamux", "quic"],
        help=f"Muxer type (default: {DEFAULTS['muxer']})",
    )
    parser.add_argument(
        "--image",
        type=str,
        help=f"Container image for the libp2p test node (default: {DEFAULTS['image']})",
    )
    parser.add_argument(
        "--publisher-image",
        type=str,
        default=DEFAULTS["publisher_image"],
        help=f"Container image for the publisher (default: {DEFAULTS['publisher_image']})",
    )
    parser.add_argument(
        "--with-delay",
        action="store_true",
        help="Enable network delay",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        help=f"Average link delay in milliseconds. Applied for --with-delay only (default: {DEFAULTS['delay_ms']})",
    )
    parser.add_argument(
        "--jitter-ms",
        type=int,
        help=f"Average jitter in milliseconds. Applied for --with-delay only (default: {DEFAULTS['jitter_ms']})",
    )
    parser.add_argument(
        "--with-mix-nodes",
        action="store_true",
        help="Enable mix protocol (generates PVC and mix env vars)",
    )
    parser.add_argument(
        "--num-mix",
        type=int,
        help=f"Number of mix nodes (default: {DEFAULTS['num_mix']})",
    )
    parser.add_argument(
        "--mix-d",
        type=int,
        help=f"Mix tunnel length (default: {DEFAULTS['mix_d']})",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help=f"Output directory for YAML files (default: {DEFAULTS['output_dir']})",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    mode = "with-mix" if args.with_mix_nodes else ("with-delay" if args.with_delay else "basic")

    print(f"Generating libp2p deployment YAMLs...")
    print(f"  Mode: {mode}")
    print(f"  Namespace: {args.namespace}")
    print(f"  Service: {args.servicename}")
    print(f"  StatefulSet: {args.statefulset_name}")
    print(f"  Peers: {args.peers}")
    print(f"  Muxer: {args.muxer}")
    print(f"  Image: {args.image}")
    if args.with_delay:
        print(f"  Delay: {args.delay_ms}ms ± {args.jitter_ms}ms")
    if args.with_mix_nodes:
        print(f"  Mix nodes: {args.num_mix}, Mix D: {args.mix_d}")
    print()

    generate_yamls(
        output_dir=args.output_dir,
        namespace=args.namespace,
        servicename=args.servicename,
        statefulset_name=args.statefulset_name,
        peers=args.peers,
        muxer=args.muxer,
        node_image=args.image,
        publisher_image=args.publisher_image,
        with_delay=args.with_delay,
        delay_ms=args.delay_ms,
        jitter_ms=args.jitter_ms,
        with_mix=args.with_mix_nodes,
        num_mix=args.num_mix,
        mix_d=args.mix_d,
    )
    print(f"YAML files generated in: {args.output_dir}")


if __name__ == "__main__":
    main()