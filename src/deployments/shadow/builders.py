# Builders for Shadow simulator runs.
#
# Pure data: takes config values, returns kubernetes-client objects and yaml dicts.
# No I/O, no kubectl calls. Validation-friendly with `--dry-run`.
#
# A Shadow run looks like:
#   - ConfigMap: holds the rendered `shadow.yaml` plus `traffic_sync.py` (publisher script).
#   - Job pod with:
#       - init container: pulls the dynamic-linked nim test-node image, copies `/node/main`
#         into a shared emptyDir.
#       - main container: `radiken/dst-shadow-base`, mounts the binary and the ConfigMap,
#         runs `shadow /sim/config/shadow.yaml`.
#
# See the Notion runbook "Using Shadow at DST" for background.
from pathlib import Path
from typing import Optional

from kubernetes.client import (
    V1Capabilities,
    V1ConfigMap,
    V1ConfigMapVolumeSource,
    V1Container,
    V1EmptyDirVolumeSource,
    V1Job,
    V1JobSpec,
    V1ObjectMeta,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1PersistentVolumeClaimVolumeSource,
    V1Pod,
    V1PodSpec,
    V1PodTemplateSpec,
    V1ResourceRequirements,
    V1SeccompProfile,
    V1SecurityContext,
    V1Volume,
    V1VolumeMount,
)
from ruamel.yaml import YAML

# Path to traffic_sync.py inside the 10ksim repo. Used to read the script
# contents into the ConfigMap at experiment time.
TRAFFIC_SYNC_REPO_PATH = (
    "deployment-utilities/docker_utilities/nimlibp2p/publisher_headless/traffic_sync.py"
)

# Mount targets inside the Shadow runner container.
_BIN_MOUNT = "/sim/bin"
_CONFIG_MOUNT = "/sim/config"
# PVC-backed working directory. Shadow writes shadow.data/ here so the per-host
# logs and metrics dumps land on persistent storage instead of pod stdout.
_RUN_MOUNT = "/sim/run"

# Default security context that Shadow needs. The default container security
# profile blocks LD_PRELOAD + ptrace, which Shadow's syscall interposer relies on.
_SHADOW_SECURITY = V1SecurityContext(
    seccomp_profile=V1SeccompProfile(type="Unconfined"),
    capabilities=V1Capabilities(add=["SYS_PTRACE"]),
)


def render_shadow_yaml(
    *,
    num_nodes: int,
    num_messages: int,
    msg_size_bytes: int,
    delay_seconds: float,
    sim_stop_time_s: int,
    publisher_start_s: int,
    connect_to: int = 2,
    muxer: str = "yamux",
    metrics_interval_s: int = 15,
) -> dict:
    """Build the shadow.yaml structure as a Python dict.

    Each simulated peer runs the nim test node (`./main`) with the env vars the test
    node expects in Shadow mode. The extra `publisher` host runs `traffic_sync.py`
    against the peers' HTTP `/publish` endpoints (port 8645) on `pod-N` hostnames.

    Topology is Shadow's built-in `1_gbit_switch` for now. Per-link bandwidth and
    latency variation needs a GML graph file, which we'll add when an experiment
    actually needs it.
    """
    if connect_to >= num_nodes:
        raise ValueError(f"connect_to ({connect_to}) must be smaller than num_nodes ({num_nodes}).")

    peer_env = {
        "PEERS": str(num_nodes),
        "CONNECTTO": str(connect_to),
        "SHADOWENV": "true",  # env.nim requires the literal string "true"
        "MUXER": muxer,
        # storeMetrics scrape cadence. Short so the last scrape captures the
        # post-traffic libp2p_network_bytes counter (the bandwidth metric).
        "METRICS_INTERVAL_S": str(metrics_interval_s),
    }
    peer_process = {
        "path": "./main",
        "start_time": "5s",
        # The nim test node is a long-running daemon; tell Shadow not to error
        # when it's still running at sim stop_time.
        "expected_final_state": "running",
        "environment": peer_env,
    }
    hosts = {
        f"pod-{i}": {
            "network_node_id": 0,
            "processes": [peer_process],
        }
        for i in range(num_nodes)
    }
    hosts["publisher"] = {
        "network_node_id": 0,
        "processes": [
            {
                "path": "/usr/bin/python3",
                "args": (
                    f"{_CONFIG_MOUNT}/traffic_sync.py"
                    f" --peer-selection id"
                    f" -n {num_nodes}"
                    f" -m {num_messages}"
                    f" -s {msg_size_bytes}"
                    f" -d {delay_seconds}"
                    f" -p 8645"
                ),
                "start_time": f"{publisher_start_s}s",
            }
        ],
    }
    return {
        "general": {
            "stop_time": f"{sim_stop_time_s}s",
            "progress": True,
        },
        "network": {
            "graph": {"type": "1_gbit_switch"},
        },
        "hosts": hosts,
    }


def _dump_yaml(obj: dict) -> str:
    """Serialize a dict to a YAML string using ruamel.yaml (matches the rest of 10ksim)."""
    import io

    buf = io.StringIO()
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.dump(obj, buf)
    return buf.getvalue()


def build_configmap(
    *,
    namespace: str,
    name: str,
    shadow_yaml: dict,
    traffic_sync_path: Path,
) -> V1ConfigMap:
    """Build the ConfigMap holding shadow.yaml + traffic_sync.py.

    The ConfigMap is mounted at /sim/config/ inside the runner container, so the
    Shadow process sees /sim/config/shadow.yaml and /sim/config/traffic_sync.py.
    """
    return V1ConfigMap(
        api_version="v1",
        kind="ConfigMap",
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        data={
            "shadow.yaml": _dump_yaml(shadow_yaml),
            "traffic_sync.py": traffic_sync_path.read_text(),
        },
    )


def build_shadow_job(
    *,
    namespace: str,
    name: str,
    configmap_name: str,
    pvc_name: str,
    test_node_image: str,
    shadow_base_image: str,
    node_pin: Optional[str] = None,
    cpu_request: str = "2",
    cpu_limit: str = "4",
    memory_request: str = "4Gi",
    memory_limit: str = "8Gi",
) -> V1Job:
    """Build the k8s Job that runs Shadow.

    Init container fetches the nim binary from `test_node_image` into the shared
    emptyDir. Main container is the generic Shadow runner image; it mounts the
    binary and the ConfigMap, then runs `shadow`.
    """
    init_container = V1Container(
        name="fetch-test-node",
        image=test_node_image,
        image_pull_policy="Always",
        # The test-node image's ENTRYPOINT is the binary itself; we override
        # to copy rather than run.
        command=["sh", "-c", f"cp /node/main {_BIN_MOUNT}/main && chmod +x {_BIN_MOUNT}/main"],
        volume_mounts=[V1VolumeMount(name="bin", mount_path=_BIN_MOUNT)],
    )

    # Stage the binary + shadow.yaml into the PVC-backed run dir, then exec Shadow
    # so the container's exit code is Shadow's (the Job condition reflects it).
    # Output lands in /sim/run/shadow.data on the PVC; the reader pod copies it out.
    main_command = [
        "/bin/bash",
        "-eu",
        "-c",
        (
            f"cp {_BIN_MOUNT}/main {_RUN_MOUNT}/main && "
            f"cp {_CONFIG_MOUNT}/shadow.yaml {_RUN_MOUNT}/shadow.yaml && "
            f"cd {_RUN_MOUNT} && "
            "exec shadow shadow.yaml"
        ),
    ]
    main_container = V1Container(
        name="shadow",
        image=shadow_base_image,
        image_pull_policy="Always",
        command=main_command,
        security_context=_SHADOW_SECURITY,
        resources=V1ResourceRequirements(
            requests={"cpu": cpu_request, "memory": memory_request},
            limits={"cpu": cpu_limit, "memory": memory_limit},
        ),
        volume_mounts=[
            V1VolumeMount(name="bin", mount_path=_BIN_MOUNT),
            V1VolumeMount(name="config", mount_path=_CONFIG_MOUNT),
            V1VolumeMount(name="run", mount_path=_RUN_MOUNT),
        ],
    )

    pod_spec = V1PodSpec(
        restart_policy="Never",
        init_containers=[init_container],
        containers=[main_container],
        volumes=[
            V1Volume(name="bin", empty_dir=V1EmptyDirVolumeSource()),
            V1Volume(
                name="config",
                config_map=V1ConfigMapVolumeSource(name=configmap_name, default_mode=0o755),
            ),
            V1Volume(
                name="run",
                persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name=pvc_name),
            ),
        ],
        node_selector={"kubernetes.io/hostname": node_pin} if node_pin else None,
    )

    return V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=V1ObjectMeta(name=name, namespace=namespace, labels={"app": name}),
        spec=V1JobSpec(
            backoff_limit=0,
            ttl_seconds_after_finished=86400,
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels={"app": name}),
                spec=pod_spec,
            ),
        ),
    )


def build_pvc(
    *,
    namespace: str,
    name: str,
    storage: str = "5Gi",
    storage_class: str = "longhorn",
) -> V1PersistentVolumeClaim:
    """Claim that holds Shadow's `shadow.data/` output for the run.

    ReadWriteOnce is enough: the Job and the reader pod don't run concurrently and
    are pinned to the same node, so the claim never needs a cross-node attachment.
    """
    return V1PersistentVolumeClaim(
        api_version="v1",
        kind="PersistentVolumeClaim",
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            storage_class_name=storage_class,
            resources=V1ResourceRequirements(requests={"storage": storage}),
        ),
    )


def build_log_reader_pod(
    *,
    namespace: str,
    name: str,
    pvc_name: str,
    image: str,
    node_pin: Optional[str] = None,
) -> V1Pod:
    """Short-lived pod that mounts the run PVC and sleeps so `kubectl cp` can copy
    `shadow.data/` out after the Job has finished.

    Pinned to the same node as the Job so the ReadWriteOnce claim attaches without a
    cross-node migration. Reuses the Shadow base image since it already has `tar`
    (needed by `kubectl cp`) and is cached on the node from the run.
    """
    return V1Pod(
        api_version="v1",
        kind="Pod",
        metadata=V1ObjectMeta(name=name, namespace=namespace, labels={"app": name}),
        spec=V1PodSpec(
            restart_policy="Never",
            containers=[
                V1Container(
                    name="reader",
                    image=image,
                    command=["sleep", "3600"],
                    volume_mounts=[V1VolumeMount(name="run", mount_path=_RUN_MOUNT)],
                )
            ],
            volumes=[
                V1Volume(
                    name="run",
                    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    ),
                )
            ],
            node_selector={"kubernetes.io/hostname": node_pin} if node_pin else None,
        ),
    )
