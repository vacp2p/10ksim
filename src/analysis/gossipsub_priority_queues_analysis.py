"""
GossipSub Priority Queues Analysis

Analyzes message delivery delays from pod logs for GossipSub priority queues experiments.
Uses VictoriaLogs to query pod logs and generates boxplot visualizations.

For metrics (queue lengths, drops, peer scores, bandwidth), use Grafana dashboard.

Usage:
    python src/analysis/gossipsub_priority_queues_analysis.py \\
        --experiment-dir src/deployments/experiments/out/<timestamp>
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.mesh_analysis.analyzers.gossipsub_priority_queues_analyzer import (
    GossipsubPriorityQueuesAnalyzer,
)
from src.analysis.utils.log_utils import init_logger

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Analyze GossipSub Priority Queues experiment")
    parser.add_argument(
        "--experiment-dir",
        required=True,
        type=Path,
        help="Path to experiment output directory containing metadata.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("analysis_output"),
        help="Output directory for analysis results",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://vlselect.lab.vac.dev/select/logsql/query",
        help="VictoriaLogs URL (default: lab.vac.dev)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        dest="verbosity",
        default=0,
        help="Increase verbosity: -v (info), -vv (debug)",
    )
    args = parser.parse_args()
    init_logger(logging.getLogger(), args.verbosity or 2, None)

    metadata_file = Path(args.experiment_dir) / "metadata.json"
    if not metadata_file.exists():
        logger.error(f"metadata.json not found: {metadata_file}")
        return 1

    with open(metadata_file) as f:
        metadata = json.load(f)

    stack = metadata["stack"]
    stack["url"] = args.url
    scenario = metadata.get("params", {}).get("scenario", "unknown")
    out_dir = args.out_dir / scenario.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info(f"Scenario: {scenario} | Namespace: {stack['namespace']}")
    logger.info(f"Time: {stack['start_time']} to {stack['end_time']}")
    logger.info(f"Output: {out_dir}")
    logger.info("=" * 60)
    analyzer = (
        GossipsubPriorityQueuesAnalyzer()
        .with_data_puller(DataPuller().with_kwargs(stack))
        .with_dump_analysis_dir(out_dir)
        .with_delay_analysis(
            stateful_sets=stack.get("stateful_sets", []),
            nodes_per_ss=stack.get("nodes_per_statefulset", []),
            scenario=scenario,
        )
    )

    results = analyzer.run()

    logger.info("\n" + "=" * 60)
    for result in results:
        status_icon = "✓" if result.status == "passed" else "✗"
        logger.info(f"{status_icon} {result.name}: {result.status}")
        if result.status == "error":
            logger.error(f"  {result.error}")
        elif result.intermediates and "stats" in result.intermediates:
            for group, stats in result.intermediates["stats"].items():
                logger.info(f"  {group}: {stats}")

    logger.info("=" * 60)
    logger.info(f"Results: {out_dir}")
    logger.info("Metrics: Use Grafana dashboard")

    return 0


if __name__ == "__main__":
    sys.exit(main())
