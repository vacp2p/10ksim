# Load a Shadow run's per-peer /metrics dumps into a throwaway VictoriaMetrics so the
# existing PromQL analysis (Scrapper) queries it like a k8s run. Shadow isn't scraped
# live, so storeMetrics appends timestamp-less snapshots we re-time on import.
import argparse
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import requests

from src.analysis.metrics.libp2p import gossipsub_summary
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.metrics.scrapper import Scrapper
from src.deployments.libp2p.bridge import STABLE_END_SHIFT, STABLE_START_SHIFT

logger = logging.getLogger(__name__)

# A /metrics dump starts with this line; we split concatenated snapshots on it.
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
    """Throwaway dockerized VictoriaMetrics; context manager, removed on exit. `.url`
    is the base URL to point a Scrapper / PromQL query at."""

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


RECEIVED_METRIC = "libp2p_gossipsub_received_total"  # no topic label, assumes one topic


def _received_total(snapshot: str) -> Optional[float]:
    """Value of the received counter in one snapshot, or None if it is not there."""
    for line in snapshot.splitlines():
        if line.startswith(RECEIVED_METRIC):
            return float(line.split()[-1])
    return None


def _snapshot_totals(per_peer: List[tuple]) -> List[float]:
    """Received counter summed across peers, one entry per snapshot.

    A peer's last value is carried forward past the end of its own snapshots, so a peer
    that stops reporting early cannot make the total fall and read as traffic stopping.
    """
    width = max((len(s) for _, s in per_peer), default=0)
    carried = [0.0] * len(per_peer)
    totals = []
    for index in range(width):
        for peer_index, (_, snaps) in enumerate(per_peer):
            if index < len(snaps):
                value = _received_total(snaps[index])
                if value is not None:
                    carried[peer_index] = value
        totals.append(sum(carried))
    return totals


def first_delivery_snapshot(per_peer: List[tuple]) -> Optional[int]:
    """Index of the snapshot where nodes first receive a message."""
    for index, total in enumerate(_snapshot_totals(per_peer)):
        if total > 0:
            return index
    return None


def last_delivery_snapshot(per_peer: List[tuple]) -> Optional[int]:
    """Index of the last snapshot where the received counter was still rising, which is
    where publishing stopped. Shadow logs no `publisher_messages_finished` event, but the
    counter going flat says the same thing."""
    totals = _snapshot_totals(per_peer)
    last = None
    for index in range(1, len(totals)):
        if totals[index] > totals[index - 1]:
            last = index
    return last


def settled_window(info: dict) -> tuple:
    """Settled part of the run, or all of it when the run is too short to have one.

    Shifts come from the bridge's `stable` window so the two platforms cannot drift apart.
    Shadow logs neither `start_messages` nor `publisher_messages_finished`, so both ends
    are anchored on the received counter instead: when it first rises, and when it stops
    rising. Ending on the last sample of the run instead would run the window minutes past
    the traffic, and gauges read over it would report the idle state: quic sheds its
    connections once nothing is being published, so it read 27 rather than the 250 it
    held under load.
    """
    first = info.get("first_delivery_epoch_s")
    if first is not None:
        start = first + STABLE_START_SHIFT.total_seconds()
        traffic_end = info.get("last_delivery_epoch_s") or info["last_epoch_s"]
        end = traffic_end + STABLE_END_SHIFT.total_seconds()
        if start < end:
            return start, end
    logger.warning("Run too short to have a settled window; scraping all of it")
    return info["start_epoch_s"], info["last_epoch_s"]


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
    """Import each peer's snapshots into VM, re-timed by snapshot index x interval
    (anchored near now if `start_epoch_s` is None) and tagged with the labels a k8s
    scrape adds (pod/instance/job/node/namespace) so the existing PromQL reads them
    unchanged."""
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

    requests.get(f"{vm_url}/internal/force_flush", timeout=15)  # make the import queryable now
    first = first_delivery_snapshot(per_peer)
    last_delivery = last_delivery_snapshot(per_peer)
    summary = {
        "peers": len(per_peer),
        "snapshots_posted": posted,
        "start_epoch_s": start_epoch_s,
        "last_epoch_s": last_epoch_s,
        "first_delivery_epoch_s": None if first is None else start_epoch_s + first * interval_s,
        "last_delivery_epoch_s": (
            None if last_delivery is None else start_epoch_s + last_delivery * interval_s
        ),
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
    """Import a Shadow run into an ephemeral VM and run the existing `Scrapper` against
    it, dumping the same per-metric CSVs as k8s under `<run_dir>/metrics/`."""
    hosts = hosts_dir_for_run(run_dir)
    dump_location = run_dir / "metrics"
    with EphemeralVictoriaMetrics() as vm:
        info = import_shadow_metrics(
            hosts_dir=hosts, vm_url=vm.url, namespace=namespace, interval_s=interval_s
        )
        start_epoch, end_epoch = settled_window(info)
        start_dt = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_epoch, tz=timezone.utc)
        config = (
            Nimlibp2pScrapeBuilder(
                namespace=namespace,
                dump_location=dump_location,
                rate_interval=rate_interval,
                step=step,
            )
            .with_interval(start_dt, end_dt, run_dir.name)
            .with_libp2p_metrics()
            .with_gossipsub_detail_metrics()
            .build()
        )
        config.url = f"{vm.url}/api/v1/"
        Scrapper(config=config).query_and_dump_metrics()
    logger.info(f"Dumped Shadow metrics CSVs under {dump_location}/")

    # The gossipsub control/efficiency counters are the reason to run Shadow deterministically;
    # log the per-node medians so they show up next to delivery in the run output.
    gs = gossipsub_summary.summarize(dump_location, run_dir.name)
    if gs:
        logger.info(f"Gossipsub detail (per-node median) for {run_dir.name}: {gs}")
    return dump_location


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
    for csv in sorted(p for p in dump_location.rglob("*") if p.is_file()):
        print(f"  {csv.relative_to(dump_location)}")


if __name__ == "__main__":
    main()
