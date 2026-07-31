import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import argparse
import logging
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import seaborn as sns

from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.mesh_analysis.analyzers.kad_dht_analyzer import KadDHTAnalyzer
from src.analysis.utils.log_utils import init_logger

sns.set_theme()


def plot_warmup_metrics(bootstrap_df, warmup_df):
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
    plt.show(block=False)


def plot_lookup_metrics(durations, attempted, success_rank, lookup_scores, closeness_scores):
    plt.figure()
    sns.histplot(durations, bins=40)
    plt.title("Lookup duration (ms)")
    plt.xlabel("Duration (ms)")
    plt.ylabel("Count")
    plt.show(block=False)

    plt.figure()
    sns.histplot(attempted, bins=20)
    plt.title("Attempted peers per lookup")
    plt.xlabel("Attempted peers")
    plt.ylabel("Count")
    plt.show(block=False)

    if success_rank:
        plt.figure()
        sns.histplot(success_rank, bins=20)
        plt.title("Local success rank")
        plt.xlabel("Rank")
        plt.ylabel("Count")
        plt.show(block=False)

    if lookup_scores:
        plt.figure()
        sns.histplot(lookup_scores, bins=20)
        plt.title("Lookup score (best returned rank)")
        plt.xlabel("Rank score")
        plt.ylabel("Count")
        plt.show(block=False)

    if closeness_scores:
        plt.figure()
        sns.histplot(closeness_scores, bins=20)
        plt.title("Closeness Score")
        plt.xlabel("Global Rank")
        plt.ylabel("Count")
        plt.show(block=False)


# -------------
# MAIN
# -------------
if __name__ == "__main__":
    init_logger(logging.getLogger(), verbosity=2)

    parser = argparse.ArgumentParser(description="Analyze KAD DHT Experiment logs.")
    parser.add_argument(
        "--start-time",
        type=str,
        required=True,
        help="Start time in ISO format (e.g., 2026-04-21T19:00:00Z)",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="End time in ISO format. Defaults to now.",
    )
    parser.add_argument(
        "--nodes", type=int, default=160, help="Number of nodes deployed. Default: 160."
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default="nimlibp2p",
        help="Kubernetes namespace. Default: nimlibp2p",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://vlselect.lab.vac.dev/select/logsql/query",
        help="VictoriaLogs URL.",
    )
    args = parser.parse_args()

    stack = {
        "type": "vaclab",
        "url": args.url,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "reader": "victoria",
        "stateful_sets": ["nodes", "bootstrap", "probe"],
        "nodes_per_statefulset": [args.nodes, 1, 1],
        "container_name": "pod-0",
        "namespace": args.namespace,
        "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
    }

    print(f"Initializing analyzer for namespace '{args.namespace}' ({args.nodes} nodes)")
    print(f"Time range: {args.start_time} to {args.end_time}")

    puller = DataPuller().with_kwargs(stack)

    log_analyzer = (
        KadDHTAnalyzer(
            dump_analysis_dir="local_data/simulations_data/kad-dht/",
        )
        .with_data_puller(puller)
        .with_warmup_check(bootstrap_pod="bootstrap-0")
        .with_dht_lookup_check(probe_pod="probe-0")
    )

    # Execute all checks
    results = log_analyzer.run()

    # Plotting results
    for res in results:
        if res.name == "warmup" and res.intermediates:
            plot_warmup_metrics(
                bootstrap_df=res.intermediates.get("bootstrap_df"),
                warmup_df=res.intermediates.get("warmup_df"),
            )
        elif res.name == "kad_dht_lookups" and res.intermediates:
            plot_lookup_metrics(
                durations=res.intermediates.get("durations"),
                attempted=res.intermediates.get("attempted"),
                success_rank=res.intermediates.get("success_rank"),
                lookup_scores=res.intermediates.get("lookup_scores"),
                closeness_scores=res.intermediates.get("closeness_scores"),
            )

    # Finally, show all figures together
    plt.show()
