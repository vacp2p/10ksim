# Runtime helpers for Shadow runs: poll for k8s Job completion + pull per-host logs.
#
# Kept separate from builders.py because these do I/O (kubectl + k8s API calls)
# while builders are pure data rendering.
import asyncio
import logging
import re
import subprocess
from pathlib import Path
from typing import Literal

from kubernetes.client import ApiClient, BatchV1Api, CoreV1Api

logger = logging.getLogger(__name__)

JobState = Literal["complete", "failed"]

# Markers the runner container's command writes around per-host log files. Kept
# in sync with the bash snippet in builders.build_shadow_job.
_DONE_RE = re.compile(rb"^===SHADOW_DONE_EXIT=(\d+)===$", re.MULTILINE)
_HOST_BEGIN_RE = re.compile(rb"^===SHADOW_HOST_FILE_BEGIN===(.+?)===$", re.MULTILINE)
_HOST_END_MARKER = b"===SHADOW_HOST_FILE_END==="


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


def pull_shadow_logs(
    *,
    api_client: ApiClient,
    namespace: str,
    job_name: str,
    dest_dir: Path,
) -> None:
    """Pull Shadow's output into `dest_dir`.

    Writes:
      - `shadow_stdout.log`: everything the runner container printed up to the
        `===SHADOW_DONE_EXIT===` marker. Shadow's own boot info, sim progress,
        syscall counters.
      - `shadow_data/hosts/<host>/<file>`: per-host stdout/stderr files the
        runner appended after the marker (one section per file, delimited by
        `===SHADOW_HOST_FILE_BEGIN/END===`).

    Why this shape: once the Job's pod hits Phase=Succeeded, `kubectl exec` and
    `kubectl cp` both refuse. `kubectl logs` is the only mechanism that still
    works, so the runner container streams the per-host files into its own
    stdout (with markers) as its last act, and we parse them out here.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    pod = _find_job_pod(api_client, namespace, job_name)
    logger.info(f"Pulling Shadow logs from `{namespace}/{pod}` into `{dest_dir}`")

    result = subprocess.run(
        ["kubectl", "-n", namespace, "logs", pod, "--tail=-1"],
        check=True,
        capture_output=True,
    )
    raw = result.stdout

    # Split: everything before SHADOW_DONE_EXIT is shadow's own stdout;
    # everything after is the per-host file dump (sectioned).
    done_match = _DONE_RE.search(raw)
    if not done_match:
        # The runner never reached the marker (Shadow crashed before tail loop,
        # or markers got mangled). Save the raw log unconditionally.
        (dest_dir / "shadow_stdout.log").write_bytes(raw)
        logger.warning(
            f"SHADOW_DONE_EXIT marker not found in pod logs; saved raw output to "
            f"{dest_dir / 'shadow_stdout.log'} ({len(raw)} bytes)"
        )
        return

    pre = raw[: done_match.start()]
    post = raw[done_match.end() :]
    shadow_exit_rc = int(done_match.group(1).decode())
    (dest_dir / "shadow_stdout.log").write_bytes(pre)
    logger.info(f"Shadow process exited with rc={shadow_exit_rc}")

    # Parse per-host sections. Each begins with =BEGIN===<path>= and ends with =END=.
    data_root = dest_dir / "shadow_data"
    count = 0
    for begin_match in _HOST_BEGIN_RE.finditer(post):
        host_path = begin_match.group(1).decode()  # e.g. "shadow.data/hosts/pod-0/main.1000.stdout"
        body_start = begin_match.end() + 1  # skip newline
        end_idx = post.find(_HOST_END_MARKER, body_start)
        if end_idx < 0:
            logger.warning(f"No END marker for `{host_path}`, skipping")
            continue
        # Strip the trailing newline that the runner's `echo` added before END.
        body = post[body_start:end_idx].rstrip(b"\n")
        out_path = data_root / host_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(body)
        count += 1
    logger.info(f"Saved {count} per-host log files under {data_root}/")
