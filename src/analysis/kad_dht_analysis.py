import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import argparse
import re
import hashlib
from collections import Counter
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.analysis.mesh_analysis.analyzers.kad_dht_analyzer import KadDHTAnalyzer

sns.set_theme()

# -------------
# WARMUP HELPERS
# -------------
def extract_node_index(pod_name: str) -> int:
    """Extract numeric index from a pod name like 'nodes-47'."""
    return int(pod_name.split("-")[-1])

def analyze_warmup(log_analyzer: KadDHTAnalyzer):
    print("=== Analyzing Warmup ===")
    t0 = log_analyzer.get_bootstrap_start_time(bootstrap_pod="bootstrap-0")
    print(f"Experiment start (bootstrap 'Node started'): {t0}")

    bootstrap_df, warmup_df = log_analyzer.check_warmup_times(n_jobs=4)

    if bootstrap_df.empty and warmup_df.empty:
        print("No warmup events found in the given time range.")
        return

    # Discard events from previous experiments (anything before this run's t=0)
    if not bootstrap_df.empty:
        bootstrap_df = bootstrap_df[bootstrap_df["timestamp"] >= t0].copy()
    if not warmup_df.empty:
        warmup_df = warmup_df[warmup_df["timestamp"] >= t0].copy()

    if bootstrap_df.empty and warmup_df.empty:
        print("No warmup events found after the bootstrap start time.")
        return

    # Keep only the latest event per pod
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
    plt.show(block=False)


# -------------
# LOOKUP HELPERS
# -------------
def normalize_status(status: str) -> str:
    value = (status or "").strip().lower()
    if value == "success":
        return "success"
    if "timeout" in value:
        return "timeout"
    if value == "missing":
        return "missing"
    return value or "unknown"

def get_kad_id(peer_id_b58: str) -> bytes:
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    num = 0
    for char in peer_id_b58:
        num = num * 58 + alphabet.index(char)
    raw_bytes = num.to_bytes((num.bit_length() + 7) // 8, 'big')
    pad = 0
    for char in peer_id_b58:
        if char == '1': pad += 1
        else: break
    raw_bytes = b'\x00' * pad + raw_bytes
    return hashlib.sha256(raw_bytes).digest()

def xor_distance(id1: bytes, id2: bytes) -> int:
    return int.from_bytes(id1, "big") ^ int.from_bytes(id2, "big")

def compute_closeness_score(target: str, returned_peers: list, all_pids: list):
    try:
        target_kad_id = get_kad_id(target)
    except Exception:
        return None
        
    all_pids_dists = []
    for pid in all_pids:
        try:
            all_pids_dists.append((pid, xor_distance(target_kad_id, get_kad_id(pid))))
        except Exception:
            pass
            
    all_pids_dists.sort(key=lambda x: x[1])
    global_ranks = {pid: i for i, (pid, _) in enumerate(all_pids_dists, start=1)}
    
    returned_ranks = [global_ranks[p["pid"]] for p in returned_peers if p["pid"] in global_ranks]
    if not returned_ranks:
        return None
        
    return min(returned_ranks)

def parse_peer(peer_str):
    pid_match = re.search(r"pid: ([^,]+)", peer_str)
    dist_match = re.search(r"dist: ([0-9a-fA-F]+)", peer_str)
    responded_match = re.search(r"responded: ([^,\)]+)", peer_str)
    attempts_match = re.search(r"attempts: (\d+)", peer_str)

    pid = pid_match.group(1).strip() if pid_match else None
    dist = int(dist_match.group(1), 16) if dist_match else None
    responded_raw = responded_match.group(1).strip() if responded_match else "unknown"
    attempts = int(attempts_match.group(1)) if attempts_match else 0

    return {
        "pid": pid,
        "dist": dist,
        "responded": normalize_status(responded_raw),
        "responded_raw": responded_raw,
        "attempts": attempts,
    }

def rank_best_returned_peer(peers):
    peers_with_dist = [p for p in peers if p["dist"] is not None]
    if not peers_with_dist:
        return None

    sorted_by_dist = sorted(peers_with_dist, key=lambda p: p["dist"])
    for i, peer in enumerate(sorted_by_dist, start=1):
        if peer["responded"] != "missing":
            return i
    return None

def classify_lookup(peers):
    statuses = [p["responded"] for p in peers]
    if "success" in statuses:
        return "success"
    if "timeout" in statuses:
        return "timeout"

    has_other_error = any(s not in {"success", "timeout", "missing", "unknown"} for s in statuses)
    if has_other_error:
        return "other_error"
    return "other_error" if "unknown" in statuses else "timeout"

def infer_lookup_error_type(peers):
    statuses = [p["responded"] for p in peers]
    if "success" in statuses:
        return None
    non_missing = [s for s in statuses if s != "missing"]
    if not non_missing:
        return "missing"
    counts = Counter(non_missing)
    return counts.most_common(1)[0][0]

def parse_row(row, all_pids):
    target = row[0]
    duration_ms = int(row[1])
    peers_raw = row[2]
    probe_id = row[3] if len(row) > 3 else None
    node_id = row[4] if len(row) > 4 else None

    peer_entries = re.findall(r"\(pid:.*?\)", peers_raw)
    peers = [parse_peer(p) for p in peer_entries]

    attempted_peers = [p for p in peers if p["attempts"] > 0]
    successful_peers = [p for p in peers if p["responded"] == "success"]
    failed_peers = [p for p in peers if p["responded"] not in {"success", "missing"}]
    timeout_peers = [p for p in peers if p["responded"] == "timeout"]
    missing_peers = [p for p in peers if p["responded"] == "missing"]

    sorted_by_dist = sorted([p for p in peers if p["dist"] is not None], key=lambda p: p["dist"])

    local_success_rank = None
    for i, p in enumerate(sorted_by_dist, start=1):
        if p["responded"] == "success":
            local_success_rank = i
            break

    lookup_score = rank_best_returned_peer(peers)
    closeness_score = compute_closeness_score(target, peers, all_pids)
    lookup_outcome = classify_lookup(peers)
    lookup_error_type = infer_lookup_error_type(peers)

    return {
        "target": target,
        "duration_ms": duration_ms,
        "probe_id": probe_id,
        "node_id": node_id,
        "num_peers": len(peers),
        "attempted_peers": len(attempted_peers),
        "successful_peers": len(successful_peers),
        "failed_peers": len(failed_peers),
        "timeout_peers": len(timeout_peers),
        "missing_peers": len(missing_peers),
        "best_dist": min((p["dist"] for p in peers if p["dist"] is not None), default=None),
        "best_success_dist": min((p["dist"] for p in successful_peers if p["dist"] is not None), default=None),
        "local_success_rank": local_success_rank,
        "lookup_score": lookup_score,
        "closeness_score": closeness_score,
        "lookup_outcome": lookup_outcome,
        "lookup_error_type": lookup_error_type,
        "peer_statuses": [p["responded"] for p in peers],
    }

def percentile_str(values, percentiles):
    if not values:
        return "N/A"
    return np.percentile(values, percentiles)

def pct(count, total):
    return 0.0 if total == 0 else (100.0 * count / total)

def calculate_lookups_metrics(parsed):
    total_lookups = len(parsed)
    durations = [x["duration_ms"] for x in parsed]
    attempted = [x["attempted_peers"] for x in parsed]
    successful_peers = [x["successful_peers"] for x in parsed]
    success_rank = [x["local_success_rank"] for x in parsed if x["local_success_rank"] is not None]
    lookup_scores = [x["lookup_score"] for x in parsed if x["lookup_score"] is not None]

    lookup_outcomes = Counter(x["lookup_outcome"] for x in parsed)
    lookup_error_types = Counter(
        x["lookup_error_type"] for x in parsed if x["lookup_error_type"] is not None
    )

    success_count = lookup_outcomes.get("success", 0)
    timeout_count = lookup_outcomes.get("timeout", 0)
    other_error_count = total_lookups - success_count - timeout_count

    print(f"Total lookups: {total_lookups:,}")
    print(f"Success rate: {pct(success_count, total_lookups):.2f}%")
    print(f"Timeout rate: {pct(timeout_count, total_lookups):.2f}%")
    print(f"Other errors: {pct(other_error_count, total_lookups):.2f}%")

    if lookup_error_types:
        print("Error types (failed lookups):")
        for err, cnt in lookup_error_types.most_common():
            print(f"  - {err}: {cnt:,} ({pct(cnt, total_lookups):.2f}% of all lookups)")

    print("Latency P50/P95/P99:", percentile_str(durations, [50, 95, 99]))
    print("Attempted peers P50/P95:", percentile_str(attempted, [50, 95]))
    print("Successful peers P50/P95:", percentile_str(successful_peers, [50, 95]))
    print("Local success rank P50/P95:", percentile_str(success_rank, [50, 95]))
    print("Lookup score (best returned rank) P50/P95:", percentile_str(lookup_scores, [50, 95]))

    closeness_scores = [x["closeness_score"] for x in parsed if x.get("closeness_score") is not None]
    if closeness_scores:
        print("Closeness score:")
        print(f"  P50 rank: {int(np.percentile(closeness_scores, 50))}")
        print(f"  P95 rank: {int(np.percentile(closeness_scores, 95))}")

    return durations, attempted, success_rank, lookup_scores, closeness_scores

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

def analyze_lookups(log_analyzer: KadDHTAnalyzer):
    print("\n=== Analyzing Lookups ===")
    log_lines = log_analyzer.check_kad_dht_result()
    if not log_lines:
        print("No lookup events found.")
        return

    all_pids = log_analyzer.extract_all_pids()
    parsed = [parse_row(row, all_pids) for row in log_lines]
    metrics = calculate_lookups_metrics(parsed)
    plot_lookup_metrics(*metrics)

# -------------
# MAIN
# -------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze KAD DHT Experiment logs.")
    parser.add_argument("--start-time", type=str, required=True, help="Start time in ISO format (e.g., 2026-04-21T19:00:00Z)")
    parser.add_argument("--end-time", type=str, default=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), help="End time in ISO format. Defaults to now.")
    parser.add_argument("--nodes", type=int, default=160, help="Number of nodes deployed. Default: 160.")
    parser.add_argument("--namespace", type=str, default="nimlibp2p", help="Kubernetes namespace. Default: nimlibp2p")
    parser.add_argument("--url", type=str, default="https://vlselect.lab.vac.dev/select/logsql/query", help="VictoriaLogs URL.")
    args = parser.parse_args()

    stack = {
        "type": "vaclab",
        "url": args.url,
        "start_time": args.start_time,
        "end_time": end_time,
        "reader": "victoria",
        "stateful_sets": ["nodes", "bootstrap", "probe"],
        "nodes_per_statefulset": [args.nodes, 1, 1],
        "container_name": "node",
        "namespace": args.namespace,
        "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
    }

    print(f"Initializing analyzer for namespace '{args.namespace}' ({args.nodes} nodes)")
    print(f"Time range: {args.start_time} to {end_time}")

    log_analyzer = KadDHTAnalyzer(
        dump_analysis_dir="local_data/simulations_data/kad-dht/",
    ).with_kwargs(stack)

    # 1. Analyze and plot Warmup times
    analyze_warmup(log_analyzer)
    
    # 2. Analyze and plot DHT Lookup Metrics
    analyze_lookups(log_analyzer)
    
    # Finally, show all figures together
    plt.show()

