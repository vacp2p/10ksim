# Python Imports
import logging
from typing import Self

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

# Project Imports
from src.analysis.mesh_analysis.analyzers.analyzer import AnalysisResult, Analyzer, OnFail
from src.analysis.mesh_analysis.readers.tracers.service_discovery_tracer import (
    ServiceDiscoveryTracer,
)

logger = logging.getLogger(__name__)
sns.set_theme()


class ServiceDiscoveryAnalyzer(Analyzer):
    def with_discovery_analysis(self, *, on_fail: OnFail = "stop") -> Self:
        return self._with_parameterized_check(
            self._analyze_discovery,
            on_fail=on_fail,
        )

    def _analyze_discovery(self) -> AnalysisResult:
        extra_fields = self.data_puller.kwargs.get("extra_fields")
        tracer = (
            ServiceDiscoveryTracer()
            .with_extra_fields(extra_fields)
            .with_starting_discovery_pattern()
            .with_found_peer_discovery_pattern()
        )

        stateful_sets = ["rare-discoverer"]

        # nodes_per_statefulset = self.data_puller.kwargs.get("nodes_per_statefulset", [])
        nodes_per_statefulset = [1]

        dfs = self.data_puller.get_all_node_dataframes(tracer, stateful_sets, nodes_per_statefulset)

        starting_df = self._get_trace_df(dfs, "start_discovery")
        found_df = self._get_trace_df(dfs, "found_advertiser")
        if starting_df.empty or found_df.empty:
            reason = "No service discovery start or found-peer logs were returned"
            logger.warning(reason)
            return AnalysisResult(
                name="service_discovery",
                status="skipped",
                intermediates={
                    "reason": reason,
                    "raw_dfs": dfs,
                },
            )

        discovery_df = self._build_discovery_latency_df(starting_df, found_df)
        if discovery_df.empty:
            reason = "No found-peer logs matched a preceding service discovery start"
            logger.warning(reason)
            return AnalysisResult(
                name="service_discovery",
                status="skipped",
                intermediates={
                    "reason": reason,
                    "raw_dfs": dfs,
                    "discovery_df": discovery_df,
                },
            )

        self._plot_discovery_latency(discovery_df)

        return AnalysisResult(
            name="service_discovery",
            status="passed",
            intermediates={
                "discovery_df": discovery_df,
                "raw_dfs": dfs,
            },
        )

    def _get_trace_df(self, dfs, key: str) -> pd.DataFrame:
        for stateful_set_dfs in dfs:
            trace_dfs = stateful_set_dfs.get(key, [])
            if trace_dfs:
                return trace_dfs[0]
        return pd.DataFrame()

    def _build_discovery_latency_df(self, starting_df: pd.DataFrame, found_df: pd.DataFrame):
        starting_df = starting_df.copy()
        found_df = found_df.copy()

        starting_df["starting_time"] = pd.to_datetime(starting_df["starting_time"], utc=True)
        found_df["found_time"] = pd.to_datetime(found_df["found_time"], utc=True)

        starting_df = starting_df.sort_values("starting_time")
        found_df = found_df.sort_values("found_time")
        by_columns = [
            column
            for column in ["serviceId", "kubernetes.pod_name", "kubernetes.pod_node_name"]
            if column in starting_df.columns and column in found_df.columns
        ]

        result = pd.merge_asof(
            found_df,
            starting_df,
            left_on="found_time",
            right_on="starting_time",
            by=by_columns,
            direction="backward",
        )
        result = result.dropna(subset=["starting_time"])
        result["elapsed_time"] = (
            result["found_time"] - result["starting_time"]
        ).dt.total_seconds() * 1000

        return result

    def _plot_discovery_latency(self, discovery_df: pd.DataFrame) -> None:
        discovery_df = discovery_df.copy()
        discovery_df["elapsed_time"] = pd.to_numeric(
            discovery_df["elapsed_time"],
            errors="coerce",
        )
        discovery_df = discovery_df.dropna(subset=["elapsed_time", "peerId", "serviceId"])

        if discovery_df.empty:
            logger.warning("No service discovery latency data to plot")
            return

        self._plot_discovery_latency_ecdf(discovery_df)
        self._plot_discovery_latency_heatmap(discovery_df)

    def _plot_discovery_latency_ecdf(self, discovery_df: pd.DataFrame) -> None:
        fig, ax = plt.subplots(figsize=(10, 6))
        sns.ecdfplot(
            data=discovery_df,
            x="elapsed_time",
            hue="serviceId",
            ax=ax,
        )
        ax.set_title("Service Discovery Latency")
        ax.set_xlabel("Elapsed Time (ms)")
        ax.set_ylabel("Discovered Peer/Service Pairs")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = self._dump_analysis_path / "service_discovery_latency_ecdf.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        logger.info(f"Saved service discovery ECDF plot: {path}")

    def _plot_discovery_latency_heatmap(self, discovery_df: pd.DataFrame) -> None:
        pivot_df = discovery_df.pivot_table(
            index="peerId",
            columns="serviceId",
            values="elapsed_time",
            aggfunc="first",
        )

        fig_width = max(8, min(24, 1.2 * len(pivot_df.columns)))
        fig_height = max(6, min(30, 0.35 * len(pivot_df.index)))
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        sns.heatmap(
            pivot_df,
            cmap="viridis_r",
            cbar_kws={"label": "Elapsed Time (ms)"},
            ax=ax,
        )
        ax.set_title("First Discovery Latency by Peer and Service")
        ax.set_xlabel("Service ID")
        ax.set_ylabel("Peer ID")

        plt.tight_layout()
        path = self._dump_analysis_path / "service_discovery_latency_heatmap.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        logger.info(f"Saved service discovery heatmap: {path}")
