# Runtime helpers for Shadow runs: poll for k8s Job completion + pull per-host logs.
#
# Kept separate from builders.py because these do I/O (kubectl + k8s API calls)
# while builders are pure data rendering.
import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Literal, Optional

from kubernetes.client import ApiClient, BatchV1Api, CoreV1Api
from kubernetes.client.rest import ApiException

from src.deployments.shadow.builders import _RUN_MOUNT, build_log_reader_pod

logger = logging.getLogger(__name__)

JobState = Literal["complete", "failed"]


async def wait_for_job_complete(
    *,
    api_client: ApiClient,
    namespace: str,
    job_name: str,
    timeout_s: int = 1800,
    poll_interval_s: int = 5,
) -> JobState:
    """Poll a k8s Job until it reports Complete or Failed in its conditions.

    Returns the terminal state. Raises TimeoutError if neither condition is
    reached before `timeout_s`. Mirrors what `kubectl wait --for=condition=...`
    does but works inside our async experiment flow without spawning a subprocess.
    """
    batch = BatchV1Api(api_client)
    elapsed = 0
    while elapsed < timeout_s:
        job = batch.read_namespaced_job_status(name=job_name, namespace=namespace)
        for condition in job.status.conditions or []:
            if condition.type == "Complete" and condition.status == "True":
                return "complete"
            if condition.type == "Failed" and condition.status == "True":
                return "failed"
        await asyncio.sleep(poll_interval_s)
        elapsed += poll_interval_s
    raise TimeoutError(
        f"Job `{namespace}/{job_name}` did not complete within {timeout_s}s "
        f"(last conditions: {job.status.conditions})"
    )


def _find_job_pod(api_client: ApiClient, namespace: str, job_name: str) -> str:
    """Return the name of the (most recent) pod owned by this Job."""
    core = CoreV1Api(api_client)
    pods = core.list_namespaced_pod(
        namespace=namespace, label_selector=f"job-name={job_name}"
    ).items
    if not pods:
        raise RuntimeError(f"No pods found for job `{namespace}/{job_name}`")
    pods.sort(key=lambda p: p.metadata.creation_timestamp)
    return pods[-1].metadata.name


def _wait_pod_running(
    core: CoreV1Api, namespace: str, pod_name: str, timeout_s: int, poll_interval_s: int = 3
) -> None:
    """Block until the pod is Running with its container ready."""
    elapsed = 0
    while elapsed < timeout_s:
        pod = core.read_namespaced_pod(name=pod_name, namespace=namespace)
        phase = pod.status.phase
        if phase == "Running":
            statuses = pod.status.container_statuses or []
            if statuses and all(s.ready for s in statuses):
                return
        elif phase in ("Failed", "Succeeded"):
            raise RuntimeError(f"Reader pod `{namespace}/{pod_name}` reached phase {phase}")
        time.sleep(poll_interval_s)
        elapsed += poll_interval_s
    raise TimeoutError(f"Reader pod `{namespace}/{pod_name}` not ready within {timeout_s}s")


def _flatten_host_logs(data_root: Path, dest: Path) -> int:
    """Flatten Shadow's per-host output into one `<host>.log` per host.

    Shadow runs the same test-node binary as k8s, so the log lines are identical;
    only the layout differs. The mesh_analysis FileStack/FileReader expects a flat
    folder of `<peer>.log` files, so we concatenate each host's stdout+stderr into
    `<host>.log` (skipping Shadow's `.shimlog` syscall noise). A Shadow run then
    reads like a k8s run with no analyzer changes.
    """
    hosts_dir = data_root / "shadow.data" / "hosts"
    if not hosts_dir.is_dir():
        logger.warning(f"No hosts dir at `{hosts_dir}`; skipping log flatten")
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for host_dir in sorted(p for p in hosts_dir.iterdir() if p.is_dir()):
        parts = sorted(host_dir.glob("*.stdout")) + sorted(host_dir.glob("*.stderr"))
        if not parts:
            continue
        with (dest / f"{host_dir.name}.log").open("wb") as out:
            for part in parts:
                out.write(part.read_bytes())
        count += 1
    logger.info(f"Flattened {count} host logs into `{dest}/`")
    return count


def pull_shadow_logs(
    *,
    api_client: ApiClient,
    namespace: str,
    job_name: str,
    pvc_name: str,
    reader_image: str,
    dest_dir: Path,
    node_pin: Optional[str] = None,
    reader_ready_timeout_s: int = 120,
) -> None:
    """Pull Shadow's output into `dest_dir`.

    Writes:
      - `shadow_stdout.log`: the Job pod's stdout (Shadow's boot info, sim
        progress, syscall counters), via `kubectl logs`.
      - `shadow_data/shadow.data/hosts/<host>/<file>`: the per-host stdout/stderr
        and metrics files Shadow wrote to the run PVC, copied out with `kubectl cp`.
      - `logs/<host>.log`: per-host stdout+stderr flattened into the flat layout
        the mesh_analysis FileStack expects, so the run is analyzable like a k8s run.

    The per-host files live on the run PVC rather than pod stdout, so we spin up a
    short-lived reader pod that mounts the same claim and copy the tree out of it.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    core = CoreV1Api(api_client)

    job_pod = _find_job_pod(api_client, namespace, job_name)
    logger.info(f"Pulling Shadow stdout from `{namespace}/{job_pod}`")
    result = subprocess.run(
        ["kubectl", "-n", namespace, "logs", job_pod, "--tail=-1"],
        check=True,
        capture_output=True,
    )
    (dest_dir / "shadow_stdout.log").write_bytes(result.stdout)

    reader_name = f"{job_name}-reader"
    reader = build_log_reader_pod(
        namespace=namespace,
        name=reader_name,
        pvc_name=pvc_name,
        image=reader_image,
        node_pin=node_pin,
    )
    logger.info(f"Starting reader pod `{namespace}/{reader_name}` to copy shadow.data off the PVC")
    core.create_namespaced_pod(namespace=namespace, body=reader)
    try:
        _wait_pod_running(core, namespace, reader_name, reader_ready_timeout_s)
        data_dest = dest_dir / "shadow_data"
        data_dest.mkdir(parents=True, exist_ok=True)
        src = f"{namespace}/{reader_name}:{_RUN_MOUNT}/shadow.data"
        subprocess.run(
            ["kubectl", "cp", "--retries=3", src, str(data_dest / "shadow.data")],
            check=True,
            capture_output=True,
        )
        logger.info(f"Copied shadow.data into {data_dest}/")
        _flatten_host_logs(data_dest, dest_dir / "logs")
    finally:
        try:
            core.delete_namespaced_pod(name=reader_name, namespace=namespace)
            logger.info(f"Deleted reader pod `{namespace}/{reader_name}`")
        except ApiException as e:
            logger.warning(f"Failed to delete reader pod `{reader_name}`: {e}")
