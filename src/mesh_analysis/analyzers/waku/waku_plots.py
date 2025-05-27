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


def plot_message_distribution_libp2pmix(received_summary_path: Path, sent_summary_path: Path, compare: Path,
                                        plot_title: str, dump_path: Path) -> Result[None, str]:
    if not received_summary_path.exists():
        error = f"Received summary file {received_summary_path} does not exist"
        logger.error(error)
        return Err(error)

    if not sent_summary_path.exists():
        error = f"Sent summary file {sent_summary_path} does not exist"
        logger.error(error)
        return Err(error)

    sns.set_theme()

    df = pd.read_csv(received_summary_path, parse_dates=["timestamp"])
    other_df = pd.read_csv(compare, parse_dates=["timestamp"])

    # Check unique messages and pods
    all_msgs = df['msg_id'].unique()
    all_pods = df['pod-name'].unique()

    # Create a pivot table of counts
    msg_pod_counts = df.groupby(['msg_id', 'pod-name']).size().unstack(fill_value=0)

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

    delays = df[['msg_id', 'delayMs']]

    # Group by msg_id to get the max delay (i.e., last node's reception time)
    #########
    # Assuming df is your DataFrame
    allowed_pods = {'pod-0', 'pod-1', 'pod-2', 'pod-3', 'pod-4', 'pod-5', 'pod-6', 'pod-7', 'pod-8', 'pod-9'}

    # Function to check if first non-zero delay pod is allowed
    def is_first_nonzero_allowed(group):
        non_zero = group[group['delayMs'] > 0]
        if non_zero.empty:
            return True  # No non-zero delay, so considered OK
        first_pod = non_zero.sort_values('delayMs').iloc[0]['pod-name']
        return first_pod in allowed_pods

    # Group by msg_id and count violations
    violations = df.groupby('msg_id').apply(lambda g: not is_first_nonzero_allowed(g))
    violation_count = violations.sum()

    print(f"Number of violations: {violation_count}")
    #########

    max_delays = delays.groupby('msg_id')['delayMs'].max()
    other_max_delays = other_df.groupby('msg_id')['delayMs'].max()

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
        mixnet_group = group[group['pod-name'].isin(mixnet_nodes)]
        non_mixnet_group = group[~group['pod-name'].isin(mixnet_nodes)]

        if non_mixnet_group.empty:
            return pd.Series({'mixnet_time': None, 'outside_time': None})

        mixnet_time = non_mixnet_group['delayMs'].min()
        total_time = group['delayMs'].max()
        outside_time = total_time - mixnet_time
        return pd.Series({'mixnet_time': mixnet_time, 'outside_time': outside_time})

    times = df.groupby('msg_id').apply(get_mixnet_and_outside_time).dropna()

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

def plot_message_distribution(received_summary_path: Path, plot_title: str, dump_path: Path) -> Result[
    None, str]:
    """
    Note that this function assumes that analyze_message_logs has been called, since timestamps will be checked
    from logs.
    """
    if not received_summary_path.exists():
        error = f'Received summary file {received_summary_path} does not exist'
        logger.error(error)
        return Err(error)

    sns.set_theme()

    df = pd.read_csv(received_summary_path, parse_dates=['timestamp'])
    df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)

    time_ranges = df.groupby(level='msg_hash').apply(
        lambda x: (x.index.get_level_values('timestamp').max() - x.index.get_level_values(
            'timestamp').min()).total_seconds()
    )

    time_ranges_df = time_ranges.reset_index(name='time_to_reach')

    plt.figure(figsize=(12, 6))
    ax = sns.boxplot(x='time_to_reach', data=time_ranges_df, color='skyblue')

    add_boxplot_stat_labels(ax, value_type="min")
    add_boxplot_stat_labels(ax, value_type="max")
    add_boxplot_stat_labels(ax, value_type="median")

    q1 = np.percentile(time_ranges_df['time_to_reach'], 25)
    q3 = np.percentile(time_ranges_df['time_to_reach'], 75)

    text = ax.text(y=-0.1, x=q1, s=f'{q1:.3f}', ha='center', va='center',
                   fontweight='bold', color='white', size=10)
    text.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground=ax.get_lines()[0].get_color()),
        path_effects.Normal(),
    ])
    text = ax.text(y=-0.1, x=q3, s=f'{q3:.3f}', ha='center', va='center',
                   fontweight='bold', color='white', size=10)
    text.set_path_effects([
        path_effects.Stroke(linewidth=3, foreground=ax.get_lines()[0].get_color()),
        path_effects.Normal(),
    ])

    plt.xlabel('Time to Reach All Nodes (seconds)')
    plt.title(plot_title)

    plt.savefig(dump_path)
    plt.show()

    return Ok(None)

def plot_message_distribution_mixnet(received_summary_path: Path, sent_summary_path: Path, plot_title: str,
                                     dump_path: Path) -> Result[None, str]:
    if not received_summary_path.exists():
        error = f"Received summary file {received_summary_path} does not exist"
        logger.error(error)
        return Err(error)

    if not sent_summary_path.exists():
        error = f"Sent summary file {sent_summary_path} does not exist"
        logger.error(error)
        return Err(error)

    sns.set_theme()

    df_received = pd.read_csv(received_summary_path, parse_dates=["timestamp"])
    df_received.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)

    df_sent = pd.read_csv(sent_summary_path, parse_dates=["timestamp"])
    df_sent.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)

    ###################
    for (shard, msg_hash), group in df_sent.groupby(['shard', 'msg_hash']):
        received_group = df_received.loc[shard, msg_hash]

        for i in range(0, len(group) - 1, 2):
            receiver_id = group.iloc[i]['receiver_peer_id']
            sender_id = group.iloc[i + 1]['sender_peer_id']

            # Check if the receiver_peer_id in the current row matches the sender_peer_id in the next row
            if receiver_id != sender_id:
                logger.error(
                    f"Mismatch detected at shard {shard}, msg_hash {msg_hash}, timestamp {group.index[i]}: "
                    f"{receiver_id} != {sender_id}")

        # Check that the last receiver in the received group matches the last sender in the sent data
        if received_group.iloc[-1]['receiver_peer_id'] != group.iloc[-1]['receiver_peer_id']:
            logger.error(f"Final mismatch at shard {shard}, msg_hash {msg_hash}: "
                         f"{received_group.iloc[-1]['receiver_peer_id']} != {group.iloc[-1]['sender_peer_id']}")
    ###################

    latest_received = df_received.groupby(level='msg_hash').apply(
        lambda x: x.index.get_level_values('timestamp').max()
    ).rename("last_received")

    sent_times = df_sent.groupby("msg_hash").apply(lambda x: x.index.get_level_values('timestamp').min()).rename(
        "injected_at")

    merged = pd.concat([sent_times, latest_received], axis=1, join="inner")
    merged["time_to_reach"] = (merged["last_received"] - merged["injected_at"]).dt.total_seconds()

    plt.figure(figsize=(12, 6))
    ax = sns.boxplot(x="time_to_reach", data=merged.reset_index(), color="skyblue")

    plt.xlabel('Time to Reach Node (seconds)')
    plt.title(plot_title)
    plt.savefig(dump_path)
    plt.show()

    return Ok(None)


@check_params_path_exists_by_position()
@check_params_path_exists_by_position_or_kwargs(1, 'file_path_2')
def check_time_to_reach_value_plot(
        file_path_1: Path,
        file_path_2: Optional[Path] = None,
        dump_path: Optional[Path] = None,
        threshold_value: Optional[int] = None,
        value_name: Optional[str] = None
) -> Result[None, str]:
    """
    Plot the distribution of a variable to reach a target value for one or two datasets.
    Index column should be a timestamp.

    Parameters:
        file_path_1 (Path): Path to the first CSV file containing data.
        file_path_2 (Optional[Path]): Path to the second CSV file containing data (if any).
        dump_path (Path): Path to save the generated plot.
        threshold_value (Optional[int]): Target value threshold to reach.
        value_name (Optional[str]): Name of the value for plot title.
    """

    def calculate_time_to_target(file_path: Path, threshold_value: float) -> pd.Series:
        """Calculate time to reach the target value for a given dataset."""
        df = pd.read_csv(file_path)
        df['Time'] = pd.to_datetime(df['Time'])
        df.set_index('Time', inplace=True)

        mask = df >= threshold_value
        first_reach = mask.idxmax()
        first_reach[~mask.any()] = pd.NaT  # Set to NaT if the target is never reached
        time_to_target = (first_reach - df.index[0]).dt.total_seconds()
        if time_to_target.isna().any():
            logger.warning(f'There are values in {file_path} that never reach {threshold_value}.')

        return time_to_target.dropna()

    time_to_target_1 = calculate_time_to_target(file_path_1, threshold_value)
    df_1 = pd.DataFrame({
        'Time to Target': time_to_target_1,
        'Dataset': [file_path_1.name] * len(time_to_target_1)
    })

    if file_path_2:
        time_to_target_2 = calculate_time_to_target(file_path_2, threshold_value)
        df_2 = pd.DataFrame({
            'Time to Target': time_to_target_2,
            'Dataset': [file_path_2.name] * len(time_to_target_2)
        })
        df = pd.concat([df_1, df_2])
    else:
        df = df_1

    plt.figure()
    if file_path_2:
        sns.violinplot(x=['Data'] * len(df), y="Time to Target", data=df, hue="Dataset", split=True, inner="quart")
    else:
        sns.boxplot(x=['Data'] * len(df), y="Time to Target", data=df)
    plt.title(f'Time to Reach Target Value: {value_name or "Target Value"}')
    plt.ylabel('Time to Reach Target (seconds)')
    plt.tight_layout()

    if dump_path:
        plt.savefig(dump_path)
    plt.show()

    return Ok(None)
