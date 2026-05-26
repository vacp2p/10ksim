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


class ShadowLogParseError(RuntimeError):
    """pull_shadow_logs couldn't parse the runner's markers out of pod stdout."""


# Markers the runner container's command writes around per-host log files. Kept
# in sync with the bash snippet in builders.build_shadow_job. The trailing
# `\n?` consumes the newline that `echo` adds, so the next .end() points cleanly
# at the start of the section body without needing a manual `+1`.
_DONE_RE = re.compile(rb"^===SHADOW_DONE_EXIT=(\d+)===\n?", re.MULTILINE)
_HOST_BEGIN_RE = re.compile(rb"^===SHADOW_HOST_FILE_BEGIN===(.+?)===\n?", re.MULTILINE)
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
        # the container OOM-killed, or markers got mangled). Save the raw log
        # so callers can debug, then raise so the experiment records this as
        # a real failure rather than silently treating it as success.
        raw_path = dest_dir / "shadow_stdout.log"
        raw_path.write_bytes(raw)
        raise ShadowLogParseError(
            f"SHADOW_DONE_EXIT marker not found in pod logs "
            f"(raw output saved to {raw_path}, {len(raw)} bytes)"
        )

    pre = raw[: done_match.start()]
    post = raw[done_match.end() :]
    shadow_exit_rc = int(done_match.group(1).decode())
    (dest_dir / "shadow_stdout.log").write_bytes(pre)
    if shadow_exit_rc != 0:
        # Defensive: today this also flows through the Job's Failed condition
        # so the experiment raises anyway. If the bash wrapper is ever changed
        # to mask the rc (e.g. `exit 0` instead of `exit $rc`), this warning
        # is the only signal we'd have left.
        logger.warning(f"Shadow process exited with non-zero rc={shadow_exit_rc}")
    else:
        logger.info(f"Shadow process exited with rc={shadow_exit_rc}")

    # Parse per-host sections. Each begins with =BEGIN===<path>= and ends with =END=.
    data_root = dest_dir / "shadow_data"
    count = 0
    for begin_match in _HOST_BEGIN_RE.finditer(post):
        host_path = begin_match.group(1).decode()  # e.g. "shadow.data/hosts/pod-0/main.1000.stdout"
        body_start = begin_match.end()  # regex consumed the trailing newline
        end_idx = post.find(_HOST_END_MARKER, body_start)
        if end_idx < 0:
            logger.warning(f"No END marker for `{host_path}`, skipping")
            continue
        # Strip the single trailing newline that the runner's `echo` added before
        # the END marker. Use rstrip(b"\n", count=1) semantics manually to avoid
        # losing legitimate trailing blank lines that were in the original file.
        body = post[body_start:end_idx]
        if body.endswith(b"\n"):
            body = body[:-1]
        out_path = data_root / host_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(body)
        count += 1
    logger.info(f"Saved {count} per-host log files under {data_root}/")
