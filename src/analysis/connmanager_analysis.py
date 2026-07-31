import logging
import os

import matplotlib.pyplot as plt
import seaborn as sns

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
