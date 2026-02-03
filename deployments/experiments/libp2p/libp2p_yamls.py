import argparse
import os
import sys
from pathlib import Path
from typing import Dict, Optional

# Add deployments directory to path
_SCRIPT_DIR = Path(__file__).resolve().parent
_DEPLOYMENTS_DIR = _SCRIPT_DIR.parent.parent
if str(_DEPLOYMENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_DEPLOYMENTS_DIR))

from kubernetes import client
from core.configs.statefulset import StatefulSetConfig
from core.kube_utils import get_YAML
from libp2p.builders.builders import Libp2pStatefulSetBuilder, create_mix_pvc
from libp2p.builders.publisher import Publisher, PublisherConfig


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
    "num_mix": 50,
    "mix_d": 3,
    "connect_to": 10,
}


def build_nodes(
    namespace: str,
    servicename: str,
    statefulset_name: str,
    num_nodes: int,
    peers: Optional[int] = None,
    connect_to: int = 10,
    muxer: str = "yamux",
    node_image: Optional[str] = None,
    network_delay_ms: Optional[int] = None,
    network_jitter_ms: int = 30,
    with_mix: bool = False,
    num_mix: int = 50,
    mix_d: int = 3,
) -> Dict[str, dict]:
    """Build libp2p StatefulSet specification."""
    api_client = client.ApiClient()

    def to_dict(deployment) -> dict:
        return api_client.sanitize_for_serialization(deployment)

    if peers is None:
        peers = num_nodes

    result = {}

    if with_mix:
        pvc = create_mix_pvc(namespace=namespace)
        result["pvc"] = to_dict(pvc)

    builder = Libp2pStatefulSetBuilder(config=StatefulSetConfig())
    builder.with_libp2p_config(
        name=statefulset_name,
        namespace=namespace,
        num_nodes=num_nodes,
        peers=peers,
        connect_to=connect_to,
        muxer=muxer,
        service=servicename,
        image=node_image,
    )

    if network_delay_ms is not None:
        builder.with_network_delay(
            delay_ms=network_delay_ms,
            jitter_ms=network_jitter_ms,
        )

    if with_mix:
        builder.with_mix(num_mix=num_mix, mix_d=mix_d)

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
    """Build publisher pod specification."""
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

    if "pvc" in deployments:
        pvc_path = os.path.join(output_dir, "mixpvc.yaml")
        with open(pvc_path, "w") as f:
            yaml.dump(deployments["pvc"], f)
        print(f"  Generated: {pvc_path}")

    nodes_path = os.path.join(output_dir, "nodes.yaml")
    with open(nodes_path, "w") as f:
        yaml.dump(deployments["nodes"], f)
    print(f"  Generated: {nodes_path}")

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

    parser.add_argument("--namespace", type=str, default=DEFAULTS["namespace"])
    parser.add_argument("--servicename", type=str, default=DEFAULTS["servicename"])
    parser.add_argument("--statefulset-name", type=str, default=DEFAULTS["statefulset_name"])
    parser.add_argument("--peers", type=int, default=DEFAULTS["peers"])
    parser.add_argument("--muxer", type=str, default=DEFAULTS["muxer"], choices=["mplex", "yamux", "quic"])
    parser.add_argument("--image", type=str, default=DEFAULTS["image"])
    parser.add_argument("--publisher-image", type=str, default=DEFAULTS["publisher_image"])
    parser.add_argument("--with-delay", action="store_true")
    parser.add_argument("--delay-ms", type=int, default=DEFAULTS["delay_ms"])
    parser.add_argument("--jitter-ms", type=int, default=DEFAULTS["jitter_ms"])
    parser.add_argument("--with-mix-nodes", action="store_true")
    parser.add_argument("--num-mix", type=int, default=DEFAULTS["num_mix"])
    parser.add_argument("--mix-d", type=int, default=DEFAULTS["mix_d"])
    parser.add_argument("--output-dir", type=str, default=DEFAULTS["output_dir"])

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