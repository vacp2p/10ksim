"""Shared pieces for the adverse-condition scenario analyses.

Each scenario emits the expectation-versus-result table the regression rulebook lists for it.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

import pandas as pd

from src.analysis.post_run.nimlibp2p import run_nimlibp2p_analysis

if TYPE_CHECKING:
    from src.deployments.experiments.libp2p.nimlibp2p import NimLibp2pExperiment

logger = logging.getLogger(__name__)

POD_COLUMN = "kubernetes.pod_name"
MESH_PEERS_DIR = Path("metrics") / "mesh-peers"
MESH_EXPECTATION = "between dLow (4) and dHigh (12), around D (6)"
Row = Tuple[str, str, str]


def load_deliveries(dump_dir: Path) -> pd.DataFrame:
    """One row per delivery, with the pod's ordinal and the publish time resolved."""
    df = pd.read_csv(dump_dir / "summary" / "received.csv")
    df["delayMs"] = pd.to_numeric(df["delayMs"], errors="coerce")
    df["ordinal"] = df[POD_COLUMN].str.rsplit("-", n=1).str[-1].astype(int)
    df["sent"] = pd.to_datetime(df["sentAt"])
    return df


def load_mesh_peers(run_dir: Path) -> Optional[pd.DataFrame]:
    """Scraped mesh-peer gauge as Time x pod, or None when the metrics scrape did not run."""
    files = sorted(p for p in (run_dir / MESH_PEERS_DIR).glob("*") if p.is_file())
    if not files:
        return None
    return pd.read_csv(files[0], index_col="Time", parse_dates=True)


def mesh_peers_row(
    mesh: Optional[pd.DataFrame], item: str, pods: Optional[Sequence[str]] = None
) -> Row:
    """Mesh degree at the last snapshot that reported: the final one can be past teardown."""
    missing = (item, MESH_EXPECTATION, "no mesh-peers metrics for those pods")
    if mesh is None or mesh.empty:
        return (item, MESH_EXPECTATION, "no mesh-peers metrics in the run folder")

    columns = list(mesh.columns) if pods is None else [p for p in pods if p in mesh.columns]
    if not columns:
        return missing
    reported = mesh[columns].dropna(how="all")
    if reported.empty:
        return missing

    final = reported.iloc[-1].dropna()
    if final.empty:
        return missing
    return (
        item,
        MESH_EXPECTATION,
        f"median {final.median():.0f}, range {final.min():.0f} to {final.max():.0f}",
    )


def pct(part: int, whole: int) -> str:
    return f"{part} of {whole} ({100 * part / whole:.1f}%)" if whole else f"{part} of 0"


def latency_summary(df: pd.DataFrame) -> str:
    d = df["delayMs"].dropna()
    if d.empty:
        return "no deliveries"
    return f"p50 {d.median():.0f} / p99 {d.quantile(0.99):.0f} / max {d.max():.0f} ms"


def write_table(dump_dir: Path, name: str, rows: Sequence[Row]) -> Path:
    """Write the table next to the other summaries and log it."""
    out = dump_dir / "summary" / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["item", "expectation", "result"]).to_csv(out, index=False)
    logger.info(f"{name}:")
    for item, expectation, result in rows:
        logger.info(f"  {item}: expected {expectation} | got {result}")
    return out


def event_time(events: List[dict]) -> Optional[datetime]:
    if not events:
        return None
    return datetime.strptime(events[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")


def prepare(experiment: "NimLibp2pExperiment") -> Tuple[Path, pd.DataFrame]:
    """Run the shared delivery analysis, then load what it dumped."""
    run_nimlibp2p_analysis(experiment)
    if experiment.output_folder is None:
        raise ValueError("Scenario analysis requires experiment.output_folder")
    dump_dir = experiment.output_folder / "analysis_data"
    return dump_dir, load_deliveries(dump_dir)
