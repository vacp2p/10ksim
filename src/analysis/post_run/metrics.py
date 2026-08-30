"""Scrape a finished run's metrics and draw the standard plots.

The reliability and latency analysis already runs itself, but the resource and mesh-health
half of a regression report did not: every campaign grew its own scrape-and-plot script.
These are the same figures, drawn the same way, off the run's own stable window.
"""

import logging
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from src.analysis.data.data_file_handler import DataPath
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.metrics.scrapper import Scrapper
from src.analysis.plotting.config import DataGroup, PlotConfig
from src.analysis.plotting.metrics_plotter import MetricsPlotter

logger = logging.getLogger(__name__)


class PlotSpec(NamedTuple):
    name: str
    metrics: List[str]
    ylabel: str
    scale: int
    fig_size: List[int]


STANDARD_PLOTS = [
    PlotSpec("bandwidth", ["libp2p-in", "libp2p-out"], "KBytes/s", 1000, [14, 5]),
    PlotSpec("memory", ["container-memory", "nim-gc-memory"], "MBytes", 1_000_000, [14, 5]),
    PlotSpec("connections", ["connections", "mesh-peers"], "peers per node", 1, [14, 5]),
]


def scrape_run_metrics(
    exp: dict, dump_location: Path, kube_config: Optional[str] = None, name: Optional[str] = None
) -> Path:
    """Dump the per-metric CSVs for one run's stable window."""
    builder = Nimlibp2pScrapeBuilder().with_exp(exp, extract_name=name is None)
    if name is not None:
        builder.name = name
    config = builder.with_dump_location(str(dump_location)).with_libp2p_metrics().build()
    logger.info(f"Scraping `{config.name}` metrics: {config.start} -> {config.end}")
    Scrapper(kube_config, config).query_and_dump_metrics()
    return dump_location


def plot_run_metrics(
    dumps: Dict[str, Path], out_dir: Path, xlabel: str, plots: Optional[List[PlotSpec]] = None
) -> List[Path]:
    """Box-plot each standard figure across `dumps`, keyed by series label (eg. muxer).

    Reads the scrape dump as it lies: `<dump>/<metric>/<run name>`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    configs = []
    for spec in plots or STANDARD_PLOTS:
        available = {label: dump for label, dump in dumps.items() if _has_any(dump, spec.metrics)}
        if not available:
            logger.warning(f"No data for the {spec.name} plot; skipping it")
            continue
        target = out_dir / spec.name
        configs.append(
            PlotConfig(
                name=str(target),
                metrics=spec.metrics,
                groups=[
                    DataGroup(name=label, data_paths=[DataPath(name=label, path=dump)])
                    for label, dump in available.items()
                ],
                legend_order=list(available),
                xlabel_name=xlabel,
                ylabel_name=spec.ylabel,
                scale_x=spec.scale,
                fig_size=spec.fig_size,
                outliers=False,
            )
        )
        written.append(target.with_suffix(".jpg"))

    if configs:
        MetricsPlotter(configs=configs).create_plots()
        logger.info(f"Wrote {len(configs)} plots to `{out_dir}/`")
    return written


def _has_any(dump: Path, metrics: List[str]) -> bool:
    return any((dump / metric).is_dir() or (dump / metric).is_file() for metric in metrics)
