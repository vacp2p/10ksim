# Python Imports
import re
from collections import Counter

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Project Imports
from src.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer

sns.set_theme()

def normalize_status(status: str) -> str:
    value = (status or "").strip().lower()
    if value == "success":
        return "success"
    if "timeout" in value:
        return "timeout"
    if value == "missing":
        return "missing"
    return value or "unknown"


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
    # Rank peers by XOR distance (dist). Best returned peer rank is this lookup's score.
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


def parse_row(row):
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


if __name__ == "__main__":
    stack = {
        "type": "vaclab",
        "url": "https://vlselect.lab.vac.dev/select/logsql/query",
        "start_time": "2026-03-27T17:24:09",
        "end_time": "2026-03-27T17:27:42",
        "reader": "victoria",
        "stateful_sets": ["probe"],
        "nodes_per_statefulset": [1],
        "container_name": "node",
        "namespace": "nimlibp2p",
        "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
    }

    log_analyzer = Nimlibp2pAnalyzer(
        dump_analysis_dir="local_data/simulations_data/kad-dht/",
        **stack,
    )
    log_lines = log_analyzer.check_kad_dht_result()

    parsed = [parse_row(row) for row in log_lines]

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

    plt.figure()
    sns.histplot(durations, bins=40)
    plt.title("Lookup duration (ms)")
    plt.xlabel("Duration (ms)")
    plt.ylabel("Count")
    plt.show()

    plt.figure()
    sns.histplot(attempted, bins=20)
    plt.title("Attempted peers per lookup")
    plt.xlabel("Attempted peers")
    plt.ylabel("Count")
    plt.show()

    if success_rank:
        plt.figure()
        sns.histplot(success_rank, bins=20)
        plt.title("Local success rank")
        plt.xlabel("Rank")
        plt.ylabel("Count")
        plt.show()

    if lookup_scores:
        plt.figure()
        sns.histplot(lookup_scores, bins=20)
        plt.title("Lookup score (best returned rank)")
        plt.xlabel("Rank score")
        plt.ylabel("Count")
        plt.show()
