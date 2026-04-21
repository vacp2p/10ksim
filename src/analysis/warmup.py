import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Project Imports
from src.analysis.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer

sns.set_theme()


def extract_node_index(pod_name: str) -> int:
    """Extract numeric index from a pod name like 'nodes-47'."""
    return int(pod_name.split("-")[-1])


if __name__ == "__main__":
    stack = {
        "type": "vaclab",
        "url": "https://vlselect.lab.vac.dev/select/logsql/query",
        "start_time": "2026-04-21T10:30:00Z",
        "end_time": "2026-04-21T11:00:00Z",
        "reader": "victoria",
        "stateful_sets": ["nodes"],
        "nodes_per_statefulset": [80],
        "container_name": "node",
        "namespace": "nimlibp2p",
        "extra_fields": ["kubernetes.pod_name"],
    }

    log_analyzer = Nimlibp2pAnalyzer(
        dump_analysis_dir="local_data/simulations_data/kad-dht/",
    ).with_kwargs(stack)

    # t=0 is when bootstrap-0 logs "Node started" — the most recent occurrence
    # within the time window, so historical experiments don't pollute the result.
    t0 = log_analyzer.get_bootstrap_start_time(bootstrap_pod="bootstrap-0")
    print(f"Experiment start (bootstrap 'Node started'): {t0}")

    bootstrap_df, warmup_df = log_analyzer.check_warmup_times(n_jobs=4)

    if bootstrap_df.empty and warmup_df.empty:
        print("No warmup events found in the given time range.")
        exit()

    # Discard events from previous experiments (anything before this run's t=0)
    if not bootstrap_df.empty:
        bootstrap_df = bootstrap_df[bootstrap_df["timestamp"] >= t0].copy()
    if not warmup_df.empty:
        warmup_df = warmup_df[warmup_df["timestamp"] >= t0].copy()

    if bootstrap_df.empty and warmup_df.empty:
        print("No warmup events found after the bootstrap start time.")
        exit()

    # Each node should appear at most once per event type. If multiple runs overlap
    # in the time window, keep only the latest event per pod so stale entries from
    # an earlier experiment don't create phantom completions.
    if not bootstrap_df.empty:
        bootstrap_df = (
            bootstrap_df.sort_values("timestamp")
            .groupby("kubernetes.pod_name", as_index=False)
            .last()
        )
    if not warmup_df.empty:
        warmup_df = (
            warmup_df.sort_values("timestamp")
            .groupby("kubernetes.pod_name", as_index=False)
            .last()
        )

    # Compute elapsed seconds relative to t0
    if not bootstrap_df.empty:
        bootstrap_df["elapsed_s"] = (bootstrap_df["timestamp"] - t0).dt.total_seconds()
        bootstrap_df["node_index"] = bootstrap_df["kubernetes.pod_name"].apply(extract_node_index)
        bootstrap_df.sort_values("node_index", inplace=True)

    if not warmup_df.empty:
        warmup_df["elapsed_s"] = (warmup_df["timestamp"] - t0).dt.total_seconds()
        warmup_df["node_index"] = warmup_df["kubernetes.pod_name"].apply(extract_node_index)
        warmup_df.sort_values("node_index", inplace=True)

    # Summary statistics
    if not bootstrap_df.empty:
        b = bootstrap_df["elapsed_s"]
        print(f"Connected to bootstrap — min: {b.min():.1f}s  median: {b.median():.1f}s  max: {b.max():.1f}s  ({len(b)} nodes)")
    if not warmup_df.empty:
        w = warmup_df["elapsed_s"]
        print(f"Warmup complete       — min: {w.min():.1f}s  median: {w.median():.1f}s  max: {w.max():.1f}s  ({len(w)} nodes)")

    # Scatter plot
    fig, ax = plt.subplots(figsize=(14, 6))

    if not bootstrap_df.empty:
        ax.scatter(
            bootstrap_df["node_index"],
            bootstrap_df["elapsed_s"],
            label="Connected to bootstrap",
            alpha=0.8,
            s=80,
            marker="o",
        )

    if not warmup_df.empty:
        ax.scatter(
            warmup_df["node_index"],
            warmup_df["elapsed_s"],
            label="Warmup complete",
            alpha=0.8,
            s=80,
            marker="^",
        )

    ax.set_xlabel("Node index")
    ax.set_ylabel("Time since bootstrap started (s)")
    ax.set_title("Bootstrap connection and warmup completion times per node")
    ax.legend()
    plt.tight_layout()
    plt.show()
