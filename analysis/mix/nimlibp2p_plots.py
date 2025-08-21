# Python Imports
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Optional
from pathlib import Path
from result import Ok, Err, Result
from matplotlib import pyplot as plt, patheffects as path_effects

# Project Imports
from src.utils.plot_utils import add_boxplot_stat_labels
from src.utils.path_utils import check_params_path_exists_by_position, check_params_path_exists_by_position_or_kwargs

logger = logging.getLogger(__name__)
sns.set_theme()


def plot_message_distribution_libp2pmix(received_summary_path: Path, sent_summary_path: Path, plot_title: str,
                                        dump_path: Path) -> Result[None, str]:
    if not received_summary_path.exists():
        error = f"Received summary file {received_summary_path} does not exist"
        logger.error(error)
        return Err(error)

    sns.set_theme()

    df = pd.read_csv(received_summary_path, parse_dates=["timestamp"])

    # Check unique messages and pods
    all_msgs = df['msgId'].unique()
    all_pods = df['kubernetes.pod_name'].unique()

    # Create a pivot table of counts
    msg_pod_counts = df.groupby(['msgId', 'kubernetes.pod_name']).size().unstack(fill_value=0)

    # Check for missing deliveries (i.e., zero counts)
    missing_deliveries = msg_pod_counts == 0

    # Report messages not received by all pods
    incomplete_msgs = missing_deliveries.any(axis=1)
    num_incomplete = incomplete_msgs.sum()
    if num_incomplete == 0:
        print(f"All nodes received all messages.")
    else:
        # Optionally list them:
        print("Messages not received by all nodes:")
        print(msg_pod_counts[incomplete_msgs])

    delays = df[['msgId', 'delayMs']]

    # Group by msgId to get the max delay (i.e., last node's reception time)
    #########
    # Assuming df is your DataFrame
    # These pods are part of the mixnet
    allowed_pods = {'pod-0', 'pod-1', 'pod-2', 'pod-3', 'pod-4', 'pod-5', 'pod-6', 'pod-7', 'pod-8', 'pod-9'}

    # Function to check if first non-zero delay pod is allowed
    def is_first_nonzero_allowed(group):
        non_zero = group[group['delayMs'] > 0]
        if non_zero.empty:
            return True  # No non-zero delay, so considered OK
        first_pod = non_zero.sort_values('delayMs').iloc[0]['kubernetes.pod_name']
        return first_pod in allowed_pods

    # Group by msgId and count violations
    violations = df.groupby('msgId').apply(lambda g: not is_first_nonzero_allowed(g))
    violation_count = violations.sum()

    print(f"Number of violations: {violation_count}")
    #########

    max_delays = delays.groupby('msgId')['delayMs'].max()

    # Plot distribution
    plt.figure(figsize=(10, 6))

    # KDE for max delays in first experiment
    sns.kdeplot(max_delays, fill=True, label='No mix', color='skyblue', alpha=0.5)

    plt.title("KDE of Max Message Propagation Time (ms)")
    plt.xlabel("Time until last node received the message (ms)")
    plt.ylabel("Density")
    plt.legend()
    plt.grid(True)
    plt.xlim(0, None)
    plt.tight_layout()
    plt.savefig(dump_path / "distribution_comparison_kde.png")
    plt.show()

    mixnet_prefix = "pod-"
    mixnet_range = 10
    # Identify mixnet nodes
    mixnet_nodes = {f"{mixnet_prefix}{i}" for i in range(mixnet_range)}  # Assumes order matters

    def get_mixnet_and_outside_time(group):
        mixnet_group = group[group['kubernetes.pod_name'].isin(mixnet_nodes)]
        non_mixnet_group = group[~group['kubernetes.pod_name'].isin(mixnet_nodes)]

        if non_mixnet_group.empty:
            return pd.Series({'mixnet_time': None, 'outside_time': None})

        mixnet_time = non_mixnet_group['delayMs'].min()
        total_time = group['delayMs'].max()
        outside_time = total_time - mixnet_time
        return pd.Series({'mixnet_time': mixnet_time, 'outside_time': outside_time})

    times = df.groupby('msgId').apply(get_mixnet_and_outside_time).dropna()

    plt.figure(figsize=(10, 6))

    # KDE area plot for mixnet delay
    sns.kdeplot(times['mixnet_time'], fill=True, label='Mixnet Time', color='orange', alpha=0.6)

    # KDE area plot for outside delay
    sns.kdeplot(times['outside_time'], fill=True, label='Outside Time', color='skyblue', alpha=0.6)

    plt.title("KDE Area Plot of Mixnet vs Outside Message Delay")
    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(dump_path / "kde.png")
    plt.show()

    return Ok(None)


@check_params_path_exists_by_position(0)
@check_params_path_exists_by_position(1)
def plot_compare_message_distribution_libp2pmix(file_1: Path, file_2: Path, plot_title: str,
                                                dump_path: Path) -> Result[None, str]:
    df_1 = pd.read_csv(file_1, parse_dates=["timestamp"])
    df_2 = pd.read_csv(file_2, parse_dates=["timestamp"])

    # Check unique messages and pods
    all_msgs = df_1['msgId'].unique()
    all_pods = df_1['kubernetes.pod_name'].unique()

    # Create a pivot table of counts
    msg_pod_counts = df_1.groupby(['msgId', 'kubernetes.pod_name']).size().unstack(fill_value=0)

    # Check for missing deliveries (i.e., zero counts)
    missing_deliveries = msg_pod_counts == 0

    # Report messages not received by all pods
    incomplete_msgs = missing_deliveries.any(axis=1)
    num_incomplete = incomplete_msgs.sum()
    if num_incomplete == 0:
        print(f"All nodes received all messages.")
    else:
        # Optionally list them:
        print("Messages not received by all nodes:")
        print(msg_pod_counts[incomplete_msgs])

    delays = df_1[['msgId', 'delayMs']]

    # Group by msgId to get the max delay (i.e., last node's reception time)
    #########
    # Assuming df is your DataFrame
    allowed_pods = {'pod-0', 'pod-1', 'pod-2', 'pod-3', 'pod-4', 'pod-5', 'pod-6', 'pod-7', 'pod-8', 'pod-9'}

    # Function to check if first non-zero delay pod is allowed
    def is_first_nonzero_allowed(group):
        non_zero = group[group['delayMs'] > 0]
        if non_zero.empty:
            return True  # No non-zero delay, so considered OK
        first_pod = non_zero.sort_values('delayMs').iloc[0]['kubernetes.pod_name']
        return first_pod in allowed_pods

    # Group by msgId and count violations
    violations = df_1.groupby('msgId').apply(lambda g: not is_first_nonzero_allowed(g))
    violation_count = violations.sum()

    print(f"Number of violations: {violation_count}")
    #########

    max_delays = delays.groupby('msgId')['delayMs'].max()
    other_max_delays = df_2.groupby('msgId')['delayMs'].max()

    # Plot distribution
    plt.figure(figsize=(10, 6))

    # KDE for max delays in first experiment
    sns.kdeplot(max_delays, fill=True, label='No mix', color='skyblue', alpha=0.5)

    # KDE for max delays in second experiment
    sns.kdeplot(other_max_delays, fill=True, label='Mix', color='salmon', alpha=0.5)

    plt.title("KDE of Max Message Propagation Time (ms)")
    plt.xlabel("Time until last node received the message (ms)")
    plt.ylabel("Density")
    plt.legend()
    plt.grid(True)
    plt.xlim(0, None)
    plt.tight_layout()
    plt.savefig(dump_path / "distribution_comparison_kde.png")
    plt.show()

    mixnet_prefix = "pod-"
    mixnet_range = 10
    # Identify mixnet nodes
    mixnet_nodes = {f"{mixnet_prefix}{i}" for i in range(mixnet_range)}  # Assumes order matters

    def get_mixnet_and_outside_time(group):
        mixnet_group = group[group['kubernetes.pod_name'].isin(mixnet_nodes)]
        non_mixnet_group = group[~group['kubernetes.pod_name'].isin(mixnet_nodes)]

        if non_mixnet_group.empty:
            return pd.Series({'mixnet_time': None, 'outside_time': None})

        mixnet_time = non_mixnet_group['delayMs'].min()
        total_time = group['delayMs'].max()
        outside_time = total_time - mixnet_time
        return pd.Series({'mixnet_time': mixnet_time, 'outside_time': outside_time})

    times = df_1.groupby('msgId').apply(get_mixnet_and_outside_time).dropna()

    plt.figure(figsize=(10, 6))

    # KDE area plot for mixnet delay
    sns.kdeplot(times['mixnet_time'], fill=True, label='Mixnet Time', color='orange', alpha=0.6)

    # KDE area plot for outside delay
    sns.kdeplot(times['outside_time'], fill=True, label='Outside Time', color='skyblue', alpha=0.6)

    plt.title("KDE Area Plot of Mixnet vs Outside Message Delay")
    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(dump_path / "kde.png")
    plt.show()

    return Ok(None)


@check_params_path_exists_by_position(0)
@check_params_path_exists_by_position(1)
def plot_in_out_mix_times():

    df = pd.read_csv(received_summary_path, parse_dates=["timestamp"])

    # Check unique messages and pods
    all_msgs = df['msgId'].unique()
    all_pods = df['kubernetes.pod_name'].unique()

    # Create a pivot table of counts
    msg_pod_counts = df.groupby(['msgId', 'kubernetes.pod_name']).size().unstack(fill_value=0)

    # Check for missing deliveries (i.e., zero counts)
    missing_deliveries = msg_pod_counts == 0

    # Report messages not received by all pods
    incomplete_msgs = missing_deliveries.any(axis=1)
    num_incomplete = incomplete_msgs.sum()
    if num_incomplete == 0:
        print(f"All nodes received all messages.")
    else:
        # Optionally list them:
        print("Messages not received by all nodes:")
        print(msg_pod_counts[incomplete_msgs])

    delays = df[['msgId', 'delayMs']]

    # Group by msgId to get the max delay (i.e., last node's reception time)
    #########
    # Assuming df is your DataFrame
    allowed_pods = {'pod-0', 'pod-1', 'pod-2', 'pod-3', 'pod-4', 'pod-5', 'pod-6', 'pod-7', 'pod-8', 'pod-9'}

    # Function to check if first non-zero delay pod is allowed
    def is_first_nonzero_allowed(group):
        non_zero = group[group['delayMs'] > 0]
        if non_zero.empty:
            return True  # No non-zero delay, so considered OK
        first_pod = non_zero.sort_values('delayMs').iloc[0]['kubernetes.pod_name']
        return first_pod in allowed_pods

    # Group by msgId and count violations
    violations = df.groupby('msgId').apply(lambda g: not is_first_nonzero_allowed(g))
    violation_count = violations.sum()

    print(f"Number of violations: {violation_count}")
    #########

    max_delays = delays.groupby('msgId')['delayMs'].max()

    mixnet_prefix = "pod-"
    mixnet_range = 10
    # Identify mixnet nodes
    mixnet_nodes = {f"{mixnet_prefix}{i}" for i in range(mixnet_range)}  # Assumes order matters

    def get_mixnet_and_outside_time(group):
        mixnet_group = group[group['kubernetes.pod_name'].isin(mixnet_nodes)]
        non_mixnet_group = group[~group['kubernetes.pod_name'].isin(mixnet_nodes)]

        if non_mixnet_group.empty:
            return pd.Series({'mixnet_time': None, 'outside_time': None})

        mixnet_time = non_mixnet_group['delayMs'].min()
        total_time = group['delayMs'].max()
        outside_time = total_time - mixnet_time
        return pd.Series({'mixnet_time': mixnet_time, 'outside_time': outside_time})

    times = df.groupby('msgId').apply(get_mixnet_and_outside_time).dropna()

    plt.figure(figsize=(10, 6))

    # KDE area plot for mixnet delay
    sns.kdeplot(times['mixnet_time'], fill=True, label='Mixnet Time', color='orange', alpha=0.6)

    # KDE area plot for outside delay
    sns.kdeplot(times['outside_time'], fill=True, label='Outside Time', color='skyblue', alpha=0.6)

    plt.title("KDE Area Plot of Mixnet vs Outside Message Delay")
    plt.xlabel("Delay (ms)")
    plt.ylabel("Density")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(dump_path / "kde.png")
    plt.show()

    return Ok(None)