import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import argparse
import logging
from datetime import datetime, timezone

import matplotlib.pyplot as plt
import seaborn as sns

from src.analysis.mesh_analysis.analyzers.connmanager_analyzer import ConnManagerAnalyzer
from src.analysis.mesh_analysis.analyzers.data_puller import DataPuller
from src.analysis.utils.log_utils import init_logger

logger = logging.getLogger(__name__)
sns.set_theme()


def plot_connection_count(conn_df, drop_df, out_dir):
    if conn_df.empty:
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.step(range(len(conn_df)), conn_df["peers"], where="post", label="Total peers")

    ax.set_xlabel("Event index")
    ax.set_ylabel("Connected peers")
    ax.set_title("Hub connection count over time")
    ax.legend()
    plt.tight_layout()
    path = os.path.join(out_dir, "connection_count.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    logger.info(f"Saved plot: {path}")


def plot_direction_breakdown(conn_df, summary, out_dir):
    if conn_df.empty:
        return

    dropped_ids = summary["dropped_ids"]
    labeled_df = summary["conn_df_labeled"].copy()
    labeled_df["status"] = labeled_df["peer_id"].apply(
        lambda pid: "dropped" if pid in dropped_ids else "survived"
    )

    group_col = (
        "wave" if "wave" in labeled_df.columns and labeled_df["wave"].nunique() > 1 else "direction"
    )
    counts = labeled_df.groupby([group_col, "status"]).size().reset_index(name="count")

    fig, ax = plt.subplots(figsize=(7, 5))
    sns.barplot(data=counts, x=group_col, y="count", hue="status", ax=ax)
    ax.set_title("Connections by group and trim outcome")
    ax.set_ylabel("Peer count")
    plt.tight_layout()
    path = os.path.join(out_dir, "direction_breakdown.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    logger.info(f"Saved plot: {path}")


def plot_trim_timeline(conn_df, drop_df, out_dir):
    if conn_df.empty or drop_df.empty:
        return

    out_df = conn_df[conn_df["direction"] == "Out"]
    in_df = conn_df[conn_df["direction"] == "In"]

    fig, ax = plt.subplots(figsize=(12, 5))

    if not out_df.empty:
        ax.scatter(
            range(len(out_df)),
            [1] * len(out_df),
            marker="|",
            s=200,
            color="steelblue",
            label="Outbound connected",
            zorder=5,
        )
    if not in_df.empty:
        ax.scatter(
            range(len(in_df)),
            [0] * len(in_df),
            marker="|",
            s=200,
            color="orange",
            label="Inbound connected",
            zorder=5,
        )
    if not drop_df.empty:
        ax.scatter(
            range(len(drop_df)),
            [-1] * len(drop_df),
            marker="x",
            s=100,
            color="red",
            label="Dropped",
            zorder=5,
        )

    ax.set_yticks([-1, 0, 1])
    ax.set_yticklabels(["Dropped", "Inbound conn", "Outbound conn"])
    ax.set_xlabel("Event index")
    ax.set_title("Connection and trim event timeline")
    ax.legend(loc="upper right")
    plt.tight_layout()
    path = os.path.join(out_dir, "trim_timeline.png")
    fig.savefig(path, dpi=120)
    plt.close(fig)
    logger.info(f"Saved plot: {path}")


if __name__ == "__main__":
    init_logger(logging.getLogger(), verbosity=2)

    parser = argparse.ArgumentParser(description="Analyze Connection Manager experiment logs.")
    parser.add_argument(
        "--run",
        default="A",
        choices=["A", "B", "C", "D", "E", "F", "G"],
        help="Experiment run to analyze",
    )
    parser.add_argument(
        "--start-time",
        required=True,
        help="Start time (ISO 8601, e.g. 2026-05-07T02:54:00Z)",
    )
    parser.add_argument(
        "--end-time",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="End time (ISO 8601). Defaults to now.",
    )
    parser.add_argument("--namespace", default="nimlibp2p", help="Kubernetes namespace")
    parser.add_argument(
        "--url",
        type=str,
        default="https://vlselect.lab.vac.dev/select/logsql/query",
        help="VictoriaLogs URL.",
    )
    parser.add_argument("-v", "--verbose", action="count", dest="verbosity", default=0)
    parser.add_argument(
        "--out-dir", default="out/connmanager", help="Directory to save plots (gitignored)"
    )
    parser.add_argument(
        "--grace-period-s", type=int, default=0, help="Grace period in seconds (Run B)"
    )
    parser.add_argument(
        "--protected-peer-ids", nargs="*", default=[], help="Known protected peer IDs (Run C)"
    )
    args = parser.parse_args()

    init_logger(logging.getLogger(), args.verbosity or 2, None)

    out_dir = os.path.join(args.out_dir, f"run_{args.run.lower()}")
    os.makedirs(out_dir, exist_ok=True)

    stack = {
        "type": "vaclab",
        "url": args.url,
        "start_time": args.start_time,
        "end_time": args.end_time,
        "reader": "victoria",
        "stateful_sets": ["hub"],
        "nodes_per_statefulset": [1],
        "container_name": "pod-0",
        "namespace": args.namespace,
        "extra_fields": ["kubernetes.pod_name"],
    }

    logger.info(f"Analyzing Run {args.run}: {args.start_time} -> {args.end_time}")
    logger.info(f"Plots will be saved to: {out_dir}")

    puller = DataPuller().with_kwargs(stack)

    wave_sets = ["wave1", "wave2"] if args.run.upper() == "B" else None

    analyzer = (
        ConnManagerAnalyzer(
            dump_analysis_dir=f"local_data/simulations_data/connmanager/run_{args.run.lower()}/",
        )
        .with_data_puller(puller)
        .with_hub_analysis(
            hub_pod="hub-0",
            grace_period_s=args.grace_period_s,
            protected_peer_ids=args.protected_peer_ids or None,
            wave_sets=wave_sets,
        )
    )

    results = analyzer.run()

    for res in results:
        if res.name == "connmanager" and res.intermediates:
            conn_df = res.intermediates.get("conn_df")
            drop_df = res.intermediates.get("drop_df")
            if conn_df is not None and not conn_df.empty:
                plot_connection_count(conn_df, drop_df, out_dir)
                plot_direction_breakdown(conn_df, res.intermediates, out_dir)
                plot_trim_timeline(conn_df, drop_df, out_dir)

    plt.show()
