import logging
from typing import List, Self

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src.analysis.mesh_analysis.analyzers.analyzer import AnalysisResult, Analyzer, OnFail
from src.analysis.utils.plot_utils import add_boxplot_stat_labels

logger = logging.getLogger(__name__)
sns.set_theme()


class GossipsubPriorityQueuesAnalyzer(Analyzer):
    """
    Analyzer for GossipSub Priority Queues experiments.
    """

    def with_delay_analysis(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[int],
        scenario: str = "unknown",
        *,
        on_fail: OnFail = "continue",
    ) -> Self:
        """
        Add message delivery delay analysis check.
        
        Args:
            stateful_sets: List of StatefulSet names (e.g., ["nimp2p", "nimp2p-slow"])
            nodes_per_ss: List of node counts per StatefulSet
            scenario: Scenario name for plot titles
            on_fail: What to do on failure ("continue" or "abort")
        """
        return self._with_parameterized_check(
            self.analyze_message_delays,
            on_fail=on_fail,
            stateful_sets=stateful_sets,
            nodes_per_ss=nodes_per_ss,
            scenario=scenario,
        )

    def analyze_message_delays(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[int],
        scenario: str = "unknown",
    ) -> AnalysisResult:
        """
        Analyze message delivery delays from logs.
        Extracts delayMs from received messages and creates boxplot visualizations.
        """
        from src.analysis.mesh_analysis.readers.tracers.nimlibp2p_tracer import Nimlibp2pTracer

        logger.info("Analyzing message delivery delays...")

        # Create tracer for received messages
        tracer = (
            Nimlibp2pTracer()
            .with_extra_fields(["kubernetes.pod_name"])
            .with_received_pattern_group()
        )

        # Get dataframes for all nodes
        dfs = self.data_puller.get_all_node_dataframes(tracer, stateful_sets, nodes_per_ss)

        # Merge all received dataframes
        received_dfs = []
        for group in dfs:
            if "received" in group:
                received_dfs.extend(group["received"])

        if not received_dfs:
            logger.warning("No received message data found")
            return AnalysisResult(
                name="delay_analysis",
                status="failed",
                intermediates={"error": "No received message data"},
            )

        delay_df = pd.concat(received_dfs, ignore_index=True)
        logger.info(f"Loaded {len(delay_df)} message reception records")

        # Dump to CSV for later analysis
        if self._dump_analysis_path:
            summary_dir = self._dump_analysis_path / "summary"
            summary_dir.mkdir(parents=True, exist_ok=True)
            received_csv = summary_dir / "received.csv"
            delay_df.to_csv(received_csv, index=False)
            logger.info(f"Saved received messages to {received_csv}")

        # Generate boxplot
        if self._dump_analysis_path:
            self._plot_delay_boxplot(delay_df, scenario)

        # Calculate statistics
        stats = self._calculate_delay_stats(delay_df)

        return AnalysisResult(
            name="delay_analysis",
            status="passed",
            intermediates={"stats": stats, "num_records": len(delay_df)},
        )

    def _calculate_delay_stats(self, delay_df: pd.DataFrame) -> dict:
        """Calculate delay statistics by pod group."""
        if delay_df.empty or "delayMs" not in delay_df.columns:
            return {}

        delay_df = delay_df.copy()
        delay_df["delayMs"] = pd.to_numeric(delay_df["delayMs"], errors="coerce")
        delay_df = delay_df.dropna(subset=["delayMs"])

        if delay_df.empty:
            return {}

        # Identify pod groups
        delay_df["pod_group"] = delay_df["kubernetes.pod_name"].apply(
            lambda x: "slow" if "slow" in str(x) else "normal"
        )

        stats = {
            "overall": {
                "min": float(delay_df["delayMs"].min()),
                "max": float(delay_df["delayMs"].max()),
                "median": float(delay_df["delayMs"].median()),
                "mean": float(delay_df["delayMs"].mean()),
                "count": len(delay_df),
            }
        }

        for group in delay_df["pod_group"].unique():
            group_data = delay_df[delay_df["pod_group"] == group]["delayMs"]
            stats[group] = {
                "min": float(group_data.min()),
                "max": float(group_data.max()),
                "median": float(group_data.median()),
                "mean": float(group_data.mean()),
                "count": len(group_data),
            }

        # Log statistics
        logger.info("Delay statistics:")
        for group_name, group_stats in stats.items():
            logger.info(
                f"  {group_name.capitalize()} - "
                f"Min: {group_stats['min']:.2f}ms, "
                f"Max: {group_stats['max']:.2f}ms, "
                f"Median: {group_stats['median']:.2f}ms, "
                f"Mean: {group_stats['mean']:.2f}ms, "
                f"Count: {group_stats['count']}"
            )

        return stats

    def _plot_delay_boxplot(self, delay_df: pd.DataFrame, scenario: str):
        """Create boxplot visualization of message delivery delays."""
        if delay_df.empty or "delayMs" not in delay_df.columns:
            logger.warning("No delay data to plot")
            return

        delay_df = delay_df.copy()
        delay_df["delayMs"] = pd.to_numeric(delay_df["delayMs"], errors="coerce")
        delay_df = delay_df.dropna(subset=["delayMs"])

        if delay_df.empty:
            logger.warning("No valid delay data after conversion")
            return

        # Identify pod groups
        delay_df["pod_group"] = delay_df["kubernetes.pod_name"].apply(
            lambda x: "slow" if "slow" in str(x) else "normal"
        )

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Boxplot by pod group
        sns.boxplot(x="pod_group", y="delayMs", data=delay_df, ax=ax1, showfliers=False)
        add_boxplot_stat_labels(ax1, value_type="min")
        add_boxplot_stat_labels(ax1, value_type="max")
        add_boxplot_stat_labels(ax1, value_type="median")
        ax1.set_ylabel("Delivery Delay (ms)")
        ax1.set_xlabel("Pod Group")
        ax1.set_title(f"Message Delivery Delay Distribution by Group - {scenario}")
        ax1.grid(True, alpha=0.3, axis="y")

        # Boxplot by individual pods (top 10 pods by message count)
        top_pods = delay_df["kubernetes.pod_name"].value_counts().head(10).index
        top_pod_data = delay_df[delay_df["kubernetes.pod_name"].isin(top_pods)]

        if not top_pod_data.empty:
            sns.boxplot(
                x="kubernetes.pod_name", y="delayMs", data=top_pod_data, ax=ax2, showfliers=False
            )
            ax2.set_ylabel("Delivery Delay (ms)")
            ax2.set_xlabel("Pod Name")
            ax2.set_title(f"Message Delivery Delay by Pod (Top 10) - {scenario}")
            ax2.tick_params(axis="x", rotation=45)
            ax2.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()
        path = self._dump_analysis_path / f"{scenario}_delivery_delay_boxplot.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        logger.info(f"Saved delay boxplot: {path}")

