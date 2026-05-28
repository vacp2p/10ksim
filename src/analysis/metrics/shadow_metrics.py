# Load Shadow per-peer metrics dumps into an ephemeral VictoriaMetrics so the
# existing metric analysis (PromQL via Scrapper) can query a Shadow run the same
# way it queries a k8s run.
#
# Shadow can't be scraped live: all peers run inside one pod on a simulated
# network, so storeMetrics appends a full /metrics snapshot to metrics_<peer>.txt
# every METRICS_INTERVAL_S. The snapshots carry no timestamps, so we synthesize
# them from snapshot order x interval and import into a throwaway VM tagged with
# pod/namespace labels. The VM is queryable exactly like the lab one.
import argparse
import logging
import subprocess
import time
from pathlib import Path
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

# Each /metrics dump starts with this line (the registry serializes in a stable
# order), so we split a concatenated metrics_<peer>.txt into snapshots on it.
_SNAPSHOT_BOUNDARY = "# HELP process_info"


def iter_snapshots(text: str) -> List[str]:
    """Split a concatenated metrics file into individual /metrics snapshots."""
    chunks: List[str] = []
    current: List[str] = []
    for line in text.splitlines(keepends=True):
        if line.startswith(_SNAPSHOT_BOUNDARY) and current:
            chunks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return [c for c in chunks if _SNAPSHOT_BOUNDARY in c]


def hosts_dir_for_run(run_dir: Path) -> Path:
    """Path to the per-host output inside a pulled Shadow run folder."""
    return run_dir / "shadow_logs" / "shadow_data" / "shadow.data" / "hosts"


class EphemeralVictoriaMetrics:
    """Run a throwaway VictoriaMetrics in Docker for the duration of an analysis.

    Use as a context manager; the container is force-removed on exit. `.url` is the
    base URL to point a Scrapper / PromQL query at.
    """

    def __init__(
        self,
        *,
        image: str = "victoriametrics/victoria-metrics:v1.103.0",
        host_port: int = 8428,
        ready_timeout_s: int = 60,
    ):
        self._image = image
        self._port = host_port
        self._ready_timeout_s = ready_timeout_s
        self._name = f"shadow-vm-{int(time.time())}"
        self.url = f"http://localhost:{host_port}"

    def __enter__(self) -> "EphemeralVictoriaMetrics":
        logger.info(f"Starting ephemeral VictoriaMetrics ({self._image}) as `{self._name}`")
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                self._name,
                "-p",
                f"{self._port}:8428",
                self._image,
            ],
            check=True,
            capture_output=True,
        )
        self._wait_ready()
        return self

    def _wait_ready(self) -> None:
        deadline = time.time() + self._ready_timeout_s
        while time.time() < deadline:
            try:
                if requests.get(f"{self.url}/health", timeout=2).ok:
                    logger.info(f"VictoriaMetrics ready at {self.url}")
                    return
            except requests.RequestException:
                pass
            time.sleep(1)
        raise TimeoutError(f"VictoriaMetrics not ready within {self._ready_timeout_s}s")

    def __exit__(self, *exc) -> None:
        subprocess.run(["docker", "rm", "-f", self._name], capture_output=True)
        logger.info(f"Removed ephemeral VictoriaMetrics `{self._name}`")


def import_shadow_metrics(
    *,
    hosts_dir: Path,
    vm_url: str,
    namespace: str,
    interval_s: int = 15,
    start_epoch_s: Optional[int] = None,
) -> dict:
    """Import every peer's snapshots into VM with synthesized timestamps + labels.

    Snapshot `k` of every peer is imported at `start_epoch_s + k*interval_s`, so the
    per-peer series line up by index. If `start_epoch_s` is None we anchor the last
    snapshot near now to stay inside VM's default retention.
    """
    metric_files = sorted(hosts_dir.glob("*/metrics_*.txt"))
    if not metric_files:
        raise FileNotFoundError(f"No metrics_*.txt under {hosts_dir}")

    per_peer = []
    max_snaps = 0
    for mf in metric_files:
        peer = mf.stem.replace("metrics_", "")  # metrics_pod-1 -> pod-1
        snaps = iter_snapshots(mf.read_text())
        if snaps:
            per_peer.append((peer, snaps))
            max_snaps = max(max_snaps, len(snaps))

    if start_epoch_s is None:
        start_epoch_s = int(time.time()) - max_snaps * interval_s

    posted = 0
    last_epoch_s = start_epoch_s
    for peer, snaps in per_peer:
        for k, snap in enumerate(snaps):
            epoch_s = start_epoch_s + k * interval_s
            last_epoch_s = max(last_epoch_s, epoch_s)
            resp = requests.post(
                f"{vm_url}/api/v1/import/prometheus",
                params={
                    "timestamp": epoch_s * 1000,
                    "extra_label": [f"pod={peer}", f"namespace={namespace}"],
                },
                data=snap.encode(),
                timeout=15,
            )
            resp.raise_for_status()
            posted += 1

    # VM ingests asynchronously; force a flush so the import is immediately queryable.
    requests.get(f"{vm_url}/internal/force_flush", timeout=15)
    summary = {"peers": len(per_peer), "snapshots_posted": posted, "last_epoch_s": last_epoch_s}
    logger.info(f"Imported Shadow metrics: {summary}")
    return summary


def query(vm_url: str, promql: str, at_epoch_s: Optional[int] = None) -> dict:
    """Run an instant PromQL query against the VM and return the parsed JSON."""
    params = {"query": promql}
    if at_epoch_s is not None:
        params["time"] = at_epoch_s
    resp = requests.get(f"{vm_url}/api/v1/query", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Load a Shadow run's metrics into an ephemeral VM and report bandwidth."
    )
    parser.add_argument(
        "run_dir", type=Path, help="Pulled Shadow run folder (contains shadow_logs/)."
    )
    parser.add_argument("--namespace", default="zerotesting-shadow")
    parser.add_argument("--interval-s", type=int, default=15)
    args = parser.parse_args()

    hosts_dir = hosts_dir_for_run(args.run_dir)
    with EphemeralVictoriaMetrics() as vm:
        info = import_shadow_metrics(
            hosts_dir=hosts_dir, vm_url=vm.url, namespace=args.namespace, interval_s=args.interval_s
        )
        result = query(
            vm.url, "sum by (direction) (libp2p_network_bytes_total)", info["last_epoch_s"]
        )
        for series in result["data"]["result"]:
            print(f"{series['metric'].get('direction')}: {series['value'][1]} bytes")


if __name__ == "__main__":
    main()
