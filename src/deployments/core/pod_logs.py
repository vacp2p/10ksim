"""Pull pod logs straight off the cluster, as a fallback for the log collector.

VictoriaLogs has intermittently shipped nothing for a namespace, which silently breaks
the whole delivery analysis. Capturing the logs with the run makes it independent of the
collector, at the cost of the dwell time it takes to pull them.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from kubernetes import client
from kubernetes.client import ApiException

logger = logging.getLogger(__name__)


def capture_pod_logs(
    namespace: str,
    dest: Path,
    api_client=None,
    *,
    label_selector: Optional[str] = None,
    workers: int = 32,
) -> int:
    """Write each pod's log to `dest/<pod>.log`. Returns how many were captured.

    Only the current container is returned, so a pod that restarted mid-run is captured
    from the restart onwards: authoritative for pods that stayed up, incomplete for the
    ones a churn scenario took down.
    """
    api = client.CoreV1Api(api_client or client.ApiClient())
    try:
        pods = api.list_namespaced_pod(namespace=namespace, label_selector=label_selector).items
    except ApiException as e:
        logger.warning(f"Could not list pods in `{namespace}` to capture logs: {e}")
        return 0

    dest.mkdir(parents=True, exist_ok=True)

    def capture(name: str) -> bool:
        try:
            log = api.read_namespaced_pod_log(name=name, namespace=namespace)
        except ApiException as e:
            logger.warning(f"Could not read logs from pod `{name}`: {e.status}")
            return False
        (dest / f"{name}.log").write_text(log)
        return True

    names = [pod.metadata.name for pod in pods]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        captured = sum(pool.map(capture, names))

    logger.info(f"Captured {captured} of {len(names)} pod logs into `{dest}/`")
    return captured
