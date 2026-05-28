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
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests

from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.metrics.scrapper import Scrapper

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
    job: str = "libp2p-nodes",
    node: str = "shadow",
) -> dict:
    """Import every peer's snapshots into VM with synthesized timestamps + labels.

    Snapshot `k` of every peer is imported at `start_epoch_s + k*interval_s`, so the
    per-peer series line up by index. If `start_epoch_s` is None we anchor the last
    snapshot near now to stay inside VM's default retention.

    Each series is tagged with the labels a k8s scrape would add (`pod`, `instance`,
    `job`, `node`, `namespace`) so the existing libp2p PromQL/extract_field analysis
    reads a Shadow run unchanged. `instance` is set to the peer so per-peer metrics
    key the same way they do off k8s scrape targets.
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
        labels = [
            f"pod={peer}",
            f"instance={peer}",
            f"namespace={namespace}",
            f"job={job}",
            f"node={node}",
        ]
        for k, snap in enumerate(snaps):
            epoch_s = start_epoch_s + k * interval_s
            last_epoch_s = max(last_epoch_s, epoch_s)
            resp = requests.post(
                f"{vm_url}/api/v1/import/prometheus",
                params={"timestamp": epoch_s * 1000, "extra_label": labels},
                data=snap.encode(),
                timeout=15,
            )
            resp.raise_for_status()
            posted += 1

    # VM ingests asynchronously; force a flush so the import is immediately queryable.
    requests.get(f"{vm_url}/internal/force_flush", timeout=15)
    summary = {
        "peers": len(per_peer),
        "snapshots_posted": posted,
        "start_epoch_s": start_epoch_s,
        "last_epoch_s": last_epoch_s,
    }
    logger.info(f"Imported Shadow metrics: {summary}")
    return summary


def scrape_run_metrics(
    *,
    run_dir: Path,
    namespace: str = "zerotesting-shadow",
    interval_s: int = 15,
    rate_interval: str = "60s",
    step: str = "15s",
) -> Path:
    """Run the full k8s metrics pipeline against a Shadow run.

    Spins up an ephemeral VM, imports the run's snapshots, then points the existing
    `Scrapper` (libp2p metric set) at it and dumps the same per-metric CSVs the k8s
    path produces, under `<run_dir>/metrics/`. Returns that dump directory.
    """
    hosts = hosts_dir_for_run(run_dir)
    dump_location = run_dir / "metrics"
    with EphemeralVictoriaMetrics() as vm:
        info = import_shadow_metrics(
            hosts_dir=hosts, vm_url=vm.url, namespace=namespace, interval_s=interval_s
        )
        start_dt = datetime.fromtimestamp(info["start_epoch_s"], tz=timezone.utc)
        end_dt = datetime.fromtimestamp(info["last_epoch_s"], tz=timezone.utc)
        config = (
            Nimlibp2pScrapeBuilder(
                namespace=namespace,
                dump_location=dump_location,
                rate_interval=rate_interval,
                step=step,
            )
            .with_interval(start_dt, end_dt, run_dir.name)
            .with_libp2p_metrics()
            .build()
        )
        config.url = f"{vm.url}/api/v1/"
        Scrapper(config=config).query_and_dump_metrics()
    logger.info(f"Dumped Shadow metrics CSVs under {dump_location}/")
    return dump_location


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

    dump_location = scrape_run_metrics(
        run_dir=args.run_dir, namespace=args.namespace, interval_s=args.interval_s
    )
    print(f"Metrics CSVs written under {dump_location}/")
    for csv in sorted(dump_location.rglob("*.csv")):
        print(f"  {csv.relative_to(dump_location)}")


if __name__ == "__main__":
    main()
