# Python Imports
import seaborn as sns
import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt


import matplotlib.pyplot as plt
import seaborn as sns

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


import matplotlib.pyplot as plt
import numpy as np


import matplotlib.pyplot as plt
import seaborn as sns

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

import matplotlib.pyplot as plt
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd

import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

import matplotlib.pyplot as plt
import seaborn as sns

import matplotlib.pyplot as plt

import seaborn as sns
import matplotlib.pyplot as plt
import logging
import numpy as np

from pandas import DataFrame
import pandas as pd
import matplotlib.pyplot as plt
from pydantic import PositiveInt
import seaborn as sns
from typing import Optional
from pathlib import Path
from result import Ok, Err, Result
from matplotlib import pyplot as plt, patheffects as path_effects
import warnings

# Project Imports
from src.utils.plot_utils import add_boxplot_stat_labels
from src.utils.path_utils import (
    check_params_path_exists_by_position,
    check_params_path_exists_by_position_or_kwargs,
)

logger = logging.getLogger(__name__)
sns.set_theme()


# Suppress all FutureWarnings
warnings.filterwarnings("ignore", category=FutureWarning)


async def plot_message_distribution_libp2pmix(
    df: DataFrame,
    sent_df: DataFrame,
    dump_path: Path,
) -> Result[None, str]:

    merged = df.merge(
        sent_df[["msgId", "kubernetes.pod_name"]],
        on=["msgId", "kubernetes.pod_name"],
        how="left",
        indicator=True,
    )

    filtered_df = merged[merged["_merge"] == "left_only"].drop(columns=["_merge"])

    pd.set_option("display.max_columns", None)

    delays = filtered_df[["msgId", "delayMs"]]
    max_delays = delays.groupby("msgId")["delayMs"].max()

    logger.debug(f"max_delays: {max_delays}")

    # Plot distribution
    plt.figure(figsize=(10, 6))

    plt.title("KDE of Max Message Propagation Time (ms)")
    try:
        dump_path.mkdir(parents=True)
    except FileExistsError:
        pass
    sns.histplot(max_delays, kde=True)
    plt.savefig(dump_path / "distribution_comparison_kde.png")

    logger.info("distribution_comparison_kde saved")


async def plot_message_distribution_libp2pmix_2(
    received_df: DataFrame,
    sent_df: DataFrame,
    mix_df: DataFrame,
    dump_path: Path,
    exp: dict,
) -> Result[None, str]:
    pd.set_option("display.max_columns", None)

    pods = pods_from_exp(exp)
    mixnet_nodes = pods["mixnet_nodes"]

    logger.debug(f"mixnet_nodes: {mixnet_nodes}")

    def classify_messages(received_df, mix_df):
        # Ensure all utc/timestamp columns are datetime
        for df, col in [(sent_df, "timestamp")]:
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = pd.to_datetime(df[col])
        if "sentAt" in received_df.columns and not pd.api.types.is_datetime64_any_dtype(
            received_df["sentAt"]
        ):
            received_df["sentAt"] = pd.to_datetime(received_df["sentAt"])

        # Get max Exit time per msgId from mix_df
        exit_times = (
            mix_df[mix_df["moment"] == "Exit"]
            .groupby("msgId")["timestamp"]
            .max()
            .rename("exit_time")
        )
        logger.debug(f"exit_times:\n{exit_times}")

        sent_time_from_sent_df = sent_df[["msgId", "timestamp"]].set_index("msgId")["timestamp"]
        sent_time_from_received_df = (
            received_df[["msgId", "sentAt"]]
            .dropna(subset=["sentAt"])
            .drop_duplicates(subset=["msgId"])
            .set_index("msgId")["sentAt"]
        )

        # Combine with preference for sent_df timestamp, else use received_df.sentAt
        send_times = sent_time_from_received_df.combine_first(sent_time_from_sent_df).rename(
            "send_time"
        )

        # Calculate mixnet delays: exit_time - send_time in ms
        valid_msgIds = exit_times.index.intersection(send_times.index)
        mixnet_delays = (
            exit_times.loc[valid_msgIds] - send_times.loc[valid_msgIds]
        ).dt.total_seconds() * 1000
        mixnet_delays.name = "mixnet_delayMs"

        def get_outside_delay(group):
            msgId = group.name
            if msgId not in exit_times:
                return None
            exit_time = exit_times[msgId]

            gossip_msgs = group[group["timestamp"] > exit_time]

            outside_delay = None
            if not gossip_msgs.empty:
                max_idx = gossip_msgs["timestamp"].idxmax()
                outside_delay = gossip_msgs.loc[max_idx, "delayMs"]

            return pd.Series({"outside_delayMs": outside_delay})

        # Get outside delays from received_df groupby
        outside_delays = received_df.groupby("msgId").apply(get_outside_delay)
        logger.debug(f"outside_delays:\n{outside_delays}")

        # Combine both delays into one DataFrame
        combined = pd.concat([mixnet_delays, outside_delays], axis=1).dropna()

        return combined.reset_index()

    times = classify_messages(received_df, mix_df)

    try:
        dump_path.mkdir(parents=True)
    except FileExistsError:
        pass

    plt.figure(figsize=(10, 6))
    sns.set_theme()

    if len(times) < 20:
        sns.scatterplot(x=range(len(times)), y=times["mixnet_delayMs"], label="Mixnet Time")
        sns.scatterplot(x=range(len(times)), y=times["outside_delayMs"], label="Outside Time")
    else:
        # KDE area plot for mixnet delay
        sns.kdeplot(
            times["mixnet_delayMs"],
            cut=0,
            fill=True,
            label="Mixnet Time",
            color="orange",
            alpha=0.6,
        )
        # KDE area plot for outside delay
        sns.kdeplot(
            times["outside_delayMs"],
            cut=0,
            fill=True,
            label="Outside Time",
            color="skyblue",
            alpha=0.6,
        )

        plt.title("KDE Area Plot of Mixnet vs Outside Message Delay")
        plt.xlabel("Delay (ms)")
        plt.ylabel("Density")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

    plt.savefig(dump_path / "kde.png")
    logger.info("kde.png saved")

    return Ok(None)


async def plot_message_distribution_libp2pmix_3(
    received_df: DataFrame,
    sent_df: DataFrame,
    mix_df: DataFrame,
    dump_path: Path,
    exp: dict,
) -> Result[None, str]:

    # Extract exit times from mix_df where moment == "Exit"
    exit_times = mix_df[mix_df["moment"] == "Exit"][["msgId", "timestamp"]].rename(
        columns={"timestamp": "exit_timestamp"}
    )

    # Merge sent_df and exit_times on msgId to get sent and exit timestamps
    merged = pd.merge(sent_df[["msgId", "timestamp"]], exit_times, on="msgId")

    # Calculate mixnet_delayMs = exit time - sent time in milliseconds
    merged["mixnet_delayMs"] = (
        merged["exit_timestamp"] - merged["timestamp"]
    ).dt.total_seconds() * 1000

    outside_delays = []

    # For each msgId, find first received timestamp after exit time and last received timestamp to compute outside delay
    for _, row in merged.iterrows():
        msgId = row["msgId"]
        exit_time = row["exit_timestamp"]
        rec_times = received_df[received_df["msgId"] == msgId]["timestamp"]

        # Filter received timestamps after exit time
        filtered = rec_times[rec_times > exit_time]

        # If none, skip
        if filtered.empty:
            continue

        start_time = filtered.min()
        end_time = rec_times.max()

        outside_delay = (end_time - start_time).total_seconds() * 1000
        outside_delays.append({"msgId": msgId, "outside_delayMs": outside_delay})

    outside_df = pd.DataFrame(outside_delays)

    # Merge outside delays with merged delays on msgId
    times = pd.merge(merged[["msgId", "mixnet_delayMs"]], outside_df, on="msgId")

    #  ------------

    try:
        dump_path.mkdir(parents=True)
    except FileExistsError:
        pass

    plt.figure(figsize=(10, 6))
    if len(times) < 30:
        sns.scatterplot(x=range(len(times)), y=times["mixnet_delayMs"], label="Mixnet Time")
        sns.scatterplot(x=range(len(times)), y=times["outside_delayMs"], label="Outside Time")
    else:
        sns.kdeplot(
            times["mixnet_delayMs"],
            cut=0,
            fill=True,
            label="Mixnet Time",
            color="orange",
            alpha=0.6,
        )
        sns.kdeplot(
            times["outside_delayMs"],
            cut=0,
            fill=True,
            label="Outside Time",
            color="skyblue",
            alpha=0.6,
        )
    plt.xlabel("Message Index")
    plt.ylabel("Delay (ms)")
    plt.title("Mixnet vs Outside Delay Distribution")
    plt.legend()

    # plt.xlabel("Delay (ms)")
    # plt.ylabel("Density")
    plt.grid(True)
    plt.tight_layout()

    plt.savefig(dump_path / "diff.png")
    logger.info("diff.png saved")

    return times


def check_exit_node_times(
    received_summary_path: Path, sent_summary_path: Path, mix_summary_path: Path
) -> Result[None, str]:
    received_df = pd.read_csv(received_summary_path, parse_dates=["timestamp", "sentAt"])
    mix_df = pd.read_csv(mix_summary_path, parse_dates=["timestamp"])
    return _check_exit_node_times(received_df, mix_df)


def _check_exit_node_times(received_df, mix_df) -> Result[None, str]:
    """
    Check that received messages occur after Exit node."""
    logger.info("--- Checking Exit vs Received times ---")

    exit_times = mix_df[mix_df["moment"] == "Exit"].set_index("msgId")["timestamp"]

    violation_count = 0

    pods_violations = {}
    msg_violations = {}

    for msgId in received_df["msgId"].unique():
        if msgId not in exit_times:
            logger.info("Messages received through gossip all occur after mixnet exit node ❌ (missing exit times)")
            return Err(f"At least one exit_time is missed. msgId: {msgId}")

        exit_time = exit_times[msgId]

        received_subset = received_df[
            (received_df["msgId"] == msgId) & (received_df["delayMs"] > 0)
        ]

        violating_pods = received_subset.loc[
            received_subset["timestamp"] < exit_time, "kubernetes.pod_name"
        ].unique()

        if len(violating_pods) > 0:
            violation_count += 1
            logger.error(f"Violation for msgId {msgId}!")

            for pod in violating_pods:
                pods_violations.setdefault(pod, []).append(msgId)
            msg_violations[msgId] = list(violating_pods)

    if violation_count:
        # Print violations per pod
        for pod, msgs in pods_violations.items():
            logger.warning(f"{pod}: {msgs}")

    if violation_count:
        logger.warning("\n")

    # Print violations per msgId
    for msgId, pods in msg_violations.items():
        logger.warning(f"{msgId}: {pods}")

    logger.warning(f"\nTotal violations: {violation_count}")

    if violation_count:
        logger.info("Messages received through gossip all occur after mixnet exit node ❌")
    else:
        logger.info("Messages received through gossip all occur after mixnet exit node ✅")

    if violation_count != 0:
        return Err("Failed exit node times check")

    return Ok(None)


def check_data(
    received_summary_path: Path,
    sent_summary_path: Path,
    mix_summary_path: Path,
    total_nodes: PositiveInt,
) -> Result[None, str]:
    """Check that all nodes receive all messages."""
    received_df = pd.read_csv(received_summary_path, parse_dates=["timestamp", "sentAt"])
    sent_df = pd.read_csv(sent_summary_path, parse_dates=["timestamp"])
    mix_df = pd.read_csv(mix_summary_path, parse_dates=["timestamp"])

    logger.info("--- Checking CSV data ---")

    all_pods = received_df["kubernetes.pod_name"].unique()
    if len(all_pods) != total_nodes:
        return Err("Not all kubernetes pods appeared in the data")

    return Ok(None)


def check_message_deliveries(
    received_summary_path: Path, sent_summary_path: Path, mix_summary_path: Path
) -> Result[None, str]:
    received_df = pd.read_csv(received_summary_path, parse_dates=["timestamp", "sentAt"])
    sent_df = pd.read_csv(sent_summary_path, parse_dates=["timestamp"])
    mix_df = pd.read_csv(mix_summary_path, parse_dates=["timestamp"])
    return _check_message_deliveries(received_df, sent_df, mix_df)


# TODO: refactor all the file IO out of all these functions.
def _check_message_deliveries(
    received_df: DataFrame, sent_df: DataFrame, mix_df: DataFrame
) -> Result[None, str]:
    """Check that all nodes receive all messages."""

    logger.info("--- Checking that all messages were delivered to all nodes ---")

    all_pods = pd.Index(received_df["kubernetes.pod_name"].unique())

    # Create a table: rows=msgId, columns=pod_name, values = count of received messages
    msg_pod_counts = received_df.pivot_table(
        index="msgId", columns="kubernetes.pod_name", aggfunc="size", fill_value=0
    )

    # For messages or pods potentially missing from received_df, reindex for completeness
    msg_pod_counts = msg_pod_counts.reindex(
        index=sent_df["msgId"].unique(), columns=all_pods, fill_value=0
    )

    total_deliveries = msg_pod_counts.values.sum()

    num_pods = len(all_pods)
    num_msgs = sent_df["msgId"].nunique()
    logger.info(
        f"Checked {num_pods} pods, {num_msgs} msgIds. Message deliveries: {total_deliveries}"
    )

    # Identify missing deliveries where count is zero
    missing_deliveries = msg_pod_counts == 0

    # Messages not received by all pods
    incomplete_msgs = missing_deliveries.any(axis=1)
    num_incomplete = incomplete_msgs.sum()

    if num_incomplete:
        logger.warning("-- missing messages by pod --")
        for pod in missing_deliveries.columns:
            missed_msgs = missing_deliveries.index[missing_deliveries[pod]].tolist()
            if missed_msgs:
                logger.warning(f"{pod}: {missed_msgs}")

        logger.warning("-- missing messages by msgId --")
        logger.warning("msgIds | pods")
        for msgId in missing_deliveries.index:
            missed_pods = missing_deliveries.columns[missing_deliveries.loc[msgId]].tolist()
            if missed_pods:
                logger.warning(f"{msgId}: {missed_pods}")

    expected_received = num_msgs * num_pods
    pass_rate = total_deliveries / expected_received
    result_str = f"{total_deliveries}/{expected_received} ({pass_rate:.2%})"
    if num_incomplete == 0:
        logger.info(f"All nodes received all messages {result_str} ✅")
    else:
        logger.info(f"All nodes received all messages {result_str} ❌")

    if num_incomplete != 0:
        return Err("Message delivery checks failed.")

    return Ok(None)


def violation_checks(
    received_summary_path: Path,
    sent_summary_path: Path,
    mix_summary_path: Path,
    total_nodes: PositiveInt,
) -> dict:
    logger.info("-- Checking for violations ---")
    data_result = check_data(
        received_summary_path, sent_summary_path, mix_summary_path, total_nodes
    )
    exit_result = check_exit_node_times(received_summary_path, sent_summary_path, mix_summary_path)
    deliveries_result = check_message_deliveries(received_summary_path, sent_summary_path, mix_summary_path)

    return {
        "data_check" : data_result,
        "exit_nodes" : exit_result,
        "message_deliveries" : deliveries_result,
    }


async def plot_message_distribution_libp2pmix_4(
    received_summary_path: Path,
    sent_summary_path: Path,
    mix_summary_path: Path,
    dump_path: Path,
    exp: dict,
) -> Result[None, None]:
    if not received_summary_path.exists():
        error = f"Received summary file {received_summary_path} does not exist"
        logger.error(error)
        return Err(error)

    sns.set_theme()

    received_df = pd.read_csv(received_summary_path, parse_dates=["timestamp", "sentAt"])
    sent_df = pd.read_csv(sent_summary_path, parse_dates=["timestamp"])
    mix_df = pd.read_csv(mix_summary_path, parse_dates=["timestamp"])

    def ensure_utc_aware(df, col):
        if not pd.api.types.is_datetime64tz_dtype(df[col]):
            # if tz-naive, localize as UTC
            df[col] = pd.to_datetime(df[col], utc=True)
        return df

    received_df = ensure_utc_aware(received_df, "sentAt")
    received_df = ensure_utc_aware(received_df, "timestamp")
    sent_df = ensure_utc_aware(sent_df, "timestamp")
    mix_df = ensure_utc_aware(mix_df, "timestamp")

    pd.set_option("display.max_columns", None)

    # -----------------

    # Extract exit timestamps per msgId
    exit_df = mix_df[mix_df["moment"] == "Exit"][["msgId", "timestamp"]].rename(
        columns={"timestamp": "exit_timestamp"}
    )

    # Get sent timestamps per msgId
    sent_times = sent_df[["msgId", "timestamp"]].rename(columns={"timestamp": "sent_timestamp"})

    # Merge exit and sent times on msgId
    merged = pd.merge(sent_times, exit_df, on="msgId", how="inner")

    records = []

    for _, row in merged.iterrows():
        msgId = row["msgId"]
        sent_time = row["sent_timestamp"]
        exit_time = row["exit_timestamp"]

        # Determine sender pod for this msgId
        sender_pod = sent_df[sent_df["msgId"] == msgId]["kubernetes.pod_name"].values[0]

        # Pods involved in this msgId in mix_df
        pods = received_df[received_df["msgId"] == msgId]["kubernetes.pod_name"].unique()

        for pod in pods:
            if pod == sender_pod:
                continue

            # Mixnet delay: only if pod present in mix_df for this msgId
            pod_mix_times = mix_df.loc[
                (mix_df["msgId"] == msgId) & (mix_df["kubernetes.pod_name"] == pod), "timestamp"
            ]
            mixnet_delay_ms = None
            if not pod_mix_times.empty:
                pod_arrival_time = pod_mix_times.min()
                mixnet_delay_ms = (pod_arrival_time - sent_time).total_seconds() * 1000

            # All received timestamps for msgId after exit time (any pod)
            pod_rec_after_exit = received_df.loc[
                (received_df["msgId"] == msgId) & (received_df["timestamp"] > exit_time),
                "timestamp",
            ]

            # All timestamps of current pod for msgId
            pod_rec_times = received_df.loc[
                (received_df["msgId"] == msgId) & (received_df["kubernetes.pod_name"] == pod),
                "timestamp",
            ]

            if pod_rec_after_exit.empty or pod_rec_times.empty:
                outside_delay_ms = None
            else:
                first_received_after_exit = pod_rec_after_exit.min()
                last_received_time = pod_rec_times.max()
                outside_delay_ms = (
                    last_received_time - first_received_after_exit
                ).total_seconds() * 1000

            # Append even if one delay is missing but other present
            if mixnet_delay_ms is not None or outside_delay_ms is not None:
                records.append(
                    {
                        "msgId": msgId,
                        "kubernetes.pod_name": pod,
                        "mixnet_delayMs": mixnet_delay_ms,
                        "outside_delayMs": outside_delay_ms,
                    }
                )

    df_delays = pd.DataFrame(records)
    df_delays_plot = df_delays.copy()

    try:
        dump_path.mkdir(parents=True)
    except FileExistsError:
        pass

    logger.debug("--- df_delays_plot ---")
    logger.debug(df_delays_plot)
    logger.debug("------")

    plt = plot_population_pyramid(df_delays_plot)
    plt.savefig(dump_path / "diff3.png")

    plt = plot_side_by_side_vertical_histograms(df_delays_plot)
    plt.savefig(dump_path / "diff4.png")

    plt = plot_side_by_side_boxplots(df_delays_plot)
    plt.savefig(dump_path / "diff5.png")

    plt = plot_side_by_side_histograms(df_delays_plot)
    plt.savefig(dump_path / "diff6.png")

    plt = plot_outside_delays(df_delays_plot)
    plt.savefig(dump_path / "diff7.png")

    plt = plot_mixnet_hop_delays_by_number(mix_df)
    plt.savefig(dump_path / "mix_hops.png")

    logger.info("diffX.png saved")

    return Ok(None)


def plot_mixnet_hop_delays_by_number(mix_df):
    logger.info("plot_mixnet_hop_delays_by_number")
    records = []

    for msgId in mix_df["msgId"].unique():
        # Get send time
        sent_time_series = mix_df.loc[
            (mix_df["msgId"] == msgId) & (mix_df["moment"] == "Sender"), "timestamp"
        ]
        if sent_time_series.empty:
            continue
        sent_time = sent_time_series.iloc[0]

        # Get hops (ordered by timestamp, not sender)
        hops = mix_df[(mix_df["msgId"] == msgId) & (mix_df["moment"] != "Sender")]
        hops = hops.sort_values("timestamp")

        prev_hop_time = sent_time
        for hop_num, (_, row) in enumerate(hops.iterrows(), 1):
            # delay relative to send
            delay_from_publish = (row["timestamp"] - sent_time).total_seconds() * 1000

            # delay relative to previous hop
            delay_from_prev_hop = (row["timestamp"] - prev_hop_time).total_seconds() * 1000

            prev_hop_time = row["timestamp"]

            records.append(
                {
                    "msgId": msgId,
                    "hop_number": hop_num,
                    "hop_pod": row["kubernetes.pod_name"],
                    "hop_moment": row["moment"],
                    "hop_delay_from_publish_ms": delay_from_publish,
                    "hop_delay_from_prev_hop_ms": delay_from_prev_hop,
                }
            )

    df_hop_delays = pd.DataFrame(records)

    # Average hop time (average of hop-to-hop delays)
    avg_hop_time = df_hop_delays["hop_delay_from_prev_hop_ms"].mean()

    logger.info("--- df_hop_delays ---")
    pd.set_option("display.expand_frame_repr", False)
    logger.info(f"\n{df_hop_delays}")
    logger.info(f"Average hop time (relative to previous hop): {avg_hop_time:.3f} ms")
    logger.info("------------")

    # Plot: hops on x, delay on y (relative to publish)
    plt.figure(figsize=(10, 6))
    sns.boxplot(x="hop_number", y="hop_delay_from_publish_ms", data=df_hop_delays, color="violet")
    plt.title("Mixnet Hop Delays by Hop Number (From Publish Time)")
    plt.xlabel("Hop Number")
    plt.ylabel("Delay (ms) from Publish")
    plt.tight_layout()

    return plt


def plot_outside_delays(df_delays):
    # sns.set(style="whitegrid")
    plt.figure(figsize=(10, 6))

    delays = df_delays["outside_delayMs"].dropna()

    sns.histplot(delays, bins=30, color="skyblue", kde=False)

    avg_delay = delays.mean()
    std_dev = delays.std()

    logger.info(f"Average Outside Delay: {avg_delay:.2f} ms")
    logger.info(f"Standard Deviation: {std_dev:.2f} ms")

    plt.title("Histogram of Outside Delays")
    plt.xlabel("Outside Delay (ms)")
    plt.ylabel("Count")
    plt.tight_layout()
    return plt


def plot_side_by_side_vertical_histograms(df_delays):
    # sns.set(style="whitegrid")

    df_melted = df_delays.melt(
        id_vars=["msgId", "kubernetes.pod_name"],
        value_vars=["mixnet_delayMs", "outside_delayMs"],
        var_name="Delay Type",
        value_name="Delay (ms)",
    )

    plt.figure(figsize=(10, 6))
    ax = sns.histplot(
        data=df_melted,
        x="Delay (ms)",
        hue="Delay Type",
        multiple="dodge",  # side by side bars
        shrink=0.8,  # bar width adjustment
        bins=30,
        palette=["orange", "skyblue"],
        edgecolor="black",
    )
    plt.title("Side-by-side Histograms of Mixnet and Outside Delays")
    plt.tight_layout()
    return plt


def plot_side_by_side_histograms(df_delays):
    # sns.set(style="whitegrid")
    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)

    # Histogram for mixnet_delayMs
    sns.histplot(df_delays["mixnet_delayMs"].dropna(), bins=20, color="orange", ax=axes[0])
    axes[0].set_title("Mixnet Delay Distribution")
    axes[0].set_xlabel("Delay (ms)")
    axes[0].set_ylabel("Count")

    # Histogram for outside_delayMs
    sns.histplot(df_delays["outside_delayMs"].dropna(), bins=30, color="skyblue", ax=axes[1])
    axes[1].set_title("Outside Delay Distribution")
    axes[1].set_xlabel("Delay (ms)")
    axes[1].set_ylabel("Count")

    plt.tight_layout()

    return plt


def plot_side_by_side_boxplots(df_delays):
    df_melted = df_delays.melt(
        id_vars=["msgId", "kubernetes.pod_name"],
        value_vars=["mixnet_delayMs", "outside_delayMs"],
        var_name="Delay Type",
        value_name="Delay (ms)",
    )

    plt.figure(figsize=(10, 6))
    ax = sns.boxplot(
        x="Delay Type",
        y="Delay (ms)",
        data=df_melted,
        showfliers=True,
        palette=["orange", "skyblue"],
    )

    plt.title("Mixnet vs Outside Delay (with outliers)")
    plt.tight_layout()

    return plt


def plot_population_pyramid(df_delays):
    mixnet_data = df_delays.dropna(subset=["mixnet_delayMs"])
    outside_data = df_delays.dropna(subset=["outside_delayMs"])

    # Create bins for the histogram (adjust bin count or edges as needed)
    max_delay = max(df_delays[["mixnet_delayMs", "outside_delayMs"]].max())
    bins = np.linspace(0, max_delay, 10)

    mixnet_counts, _ = np.histogram(mixnet_data["mixnet_delayMs"], bins=bins)
    outside_counts, _ = np.histogram(outside_data["outside_delayMs"], bins=bins)

    bin_centers = 0.5 * (bins[:-1] + bins[1:])

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot mixnet delays to the left (negative values)
    ax.barh(
        bin_centers,
        -mixnet_counts,
        height=(bins[1] - bins[0]),
        color="orange",
        label="Mixnet Delay",
    )

    # Plot outside delays to the right (positive values)
    ax.barh(
        bin_centers,
        outside_counts,
        height=(bins[1] - bins[0]),
        color="skyblue",
        label="Outside Delay",
    )

    ax.set_xlabel("Count")
    ax.set_ylabel("Delay bin (ms)")
    ax.set_title("Population Pyramid of Delay Distributions")
    ax.legend()

    # Set symmetrical x-axis limits based on max count on either side
    max_count = max(mixnet_counts.max(), outside_counts.max()) * 1.1
    ax.set_xlim(-max_count, max_count)

    # Set x-axis ticks with absolute values for clarity
    xticks = np.linspace(-max_count, max_count, 7)
    ax.set_xticks(xticks)
    ax.set_xticklabels([int(abs(x)) for x in xticks])

    plt.tight_layout()

    return plt


def plot_delay_comparisons(df_delays):
    plt.figure(figsize=(12, 6))

    # Plot step histogram for outside_delayMs (many points, blue)
    sns.histplot(
        df_delays["outside_delayMs"],
        bins=30,
        stat="density",
        element="step",
        fill=False,
        color="skyblue",
        label="Outside Delay",
    )

    # Plot step histogram for mixnet_delayMs (fewer points, orange)
    sns.histplot(
        df_delays["mixnet_delayMs"].dropna(),
        bins=15,
        stat="density",
        element="step",
        fill=False,
        color="orange",
        label="Mixnet Delay",
    )

    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.title("Comparison of Mixnet and Outside Delay Distributions")
    plt.legend()
    plt.tight_layout()

    return plt


def plot_delay_densities(df_delays):
    plt.figure(figsize=(12, 6))

    # KDE plot for outside_delayMs with separate normalization
    sns.kdeplot(
        data=df_delays,
        x="outside_delayMs",
        fill=True,
        common_norm=False,
        alpha=0.4,
        color="skyblue",
        label="Outside Delay",
        bw_adjust=1.0,
        rug=True,  # show each data point as tick marks
    )

    # KDE plot for mixnet_delayMs with separate normalization and tighter bandwidth
    sns.kdeplot(
        data=df_delays.dropna(subset=["mixnet_delayMs"]),
        x="mixnet_delayMs",
        fill=True,
        common_norm=False,
        alpha=0.8,
        color="orange",
        label="Mixnet Delay",
        bw_adjust=0.5,
        rug=True,
    )

    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.title("Normalized Density of Mixnet and Outside Delays with Rug Plots")
    plt.legend()
    plt.tight_layout()

    return plt


def plot_independent_densities(df_delays):
    # sns.set(style="whitegrid")
    plt.figure(figsize=(12, 6))

    # KDE plot for outside_delayMs (all points)
    sns.kdeplot(
        data=df_delays,
        x="outside_delayMs",
        fill=True,
        alpha=0.5,
        color="skyblue",
        label="Outside Delay",
        common_norm=False,  # Normalize each distribution independently
    )

    # KDE plot for mixnet_delayMs (drop NaN)
    sns.kdeplot(
        data=df_delays.dropna(subset=["mixnet_delayMs"]),
        x="mixnet_delayMs",
        fill=True,
        alpha=0.7,
        color="orange",
        label="Mixnet Delay",
        common_norm=False,
    )

    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.title("Independent Density Distributions of Mixnet and Outside Delays")
    plt.legend()
    plt.tight_layout()

    return plt


def pods_from_exp(exp: dict):
    mixnet_prefix = exp["mix_node_name"]
    # mixnet_range = 10 # TODO this should be part of settings
    mixnet_range = exp["num_mix_nodes"]
    # gossip_prefix = "pod-"
    gossip_prefix = exp["gossip_node_name"]
    # gossip_range = 1
    gossip_range = exp["num_gossip_nodes"]
    # Identify mixnet nodes
    mixnet_nodes = {f"{mixnet_prefix}-{i}" for i in range(mixnet_range)}  # Assumes order matters
    # gossip_nodes = {f"{gossip_prefix}{i}" for i in range(mixnet_range, mixnet_range+gossip_range)}  # Assumes order matters
    gossip_nodes = {f"{gossip_prefix}{i}" for i in range(gossip_range)}  # Assumes order matters

    return {
        "mixnet_nodes": mixnet_nodes,
        "gossip_nodes": gossip_nodes,
    }


async def plot_in_out_mix_times(received_summary_path: Path, dump_path: Path, exp: dict):
    df = pd.read_csv(received_summary_path, parse_dates=["timestamp"])

    pods = pods_from_exp(exp)
    mixnet_nodes = pods["mixnet_nodes"]
    gossip_nodes = pods["gossip_nodes"]

    allowed_pods = mixnet_nodes

    logger.debug(f"mixnet_nodes: {mixnet_nodes}")
    logger.debug(f"gossip_nodes: {gossip_nodes}")
    logger.debug(f"allowed_pods: {allowed_pods}")

    def get_mixnet_and_outside_time(group):
        mixnet_group = group[group["kubernetes.pod_name"].isin(mixnet_nodes)]
        non_mixnet_group = group[~group["kubernetes.pod_name"].isin(mixnet_nodes)]

        if non_mixnet_group.empty:
            return pd.Series({"mixnet_time": None, "outside_time": None})

        mixnet_time = non_mixnet_group["delayMs"].min()
        total_time = group["delayMs"].max()
        outside_time = total_time - mixnet_time
        # convert ns -> ms
        # mixnet_time /= 1_000_000
        # outside_time /= 1_000_000
        return pd.Series({"mixnet_time": mixnet_time, "outside_time": outside_time})

    times = df.groupby("msgId").apply(get_mixnet_and_outside_time).dropna()

    logger.debug(f"times: {times}")

    try:
        dump_path.mkdir(parents=True)
    except FileExistsError:
        pass

    plt.figure(figsize=(10, 6))

    sns.kdeplot(times["mixnet_time"], fill=True, label="Mixnet Time", color="orange", alpha=0.6)
    sns.kdeplot(times["outside_time"], fill=True, label="Outside Time", color="skyblue", alpha=0.6)

    plt.title("KDE Area Plot of Mixnet vs Outside Message Delay")
    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(dump_path / "kde.png")

    return Ok(None)
