import hashlib
import logging
import re
from collections import Counter
from typing import List, Self, Optional

import numpy as np
import pandas as pd

from src.analysis.mesh_analysis.analyzers.analyzer import AnalysisResult, Analyzer, OnFail
from src.analysis.mesh_analysis.readers.tracers.kad_dht_tracer import KadDHTTracer

logger = logging.getLogger(__name__)

# -------------
# HELPERS
# -------------
def extract_node_index(pod_name: str) -> int:
    """Extract numeric index from a pod name like 'nodes-47'."""
    return int(pod_name.split("-")[-1])

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

    logger.info(f"Total lookups: {total_lookups:,}")
    logger.info(f"Success rate: {pct(success_count, total_lookups):.2f}%")
    logger.info(f"Timeout rate: {pct(timeout_count, total_lookups):.2f}%")
    logger.info(f"Other errors: {pct(other_error_count, total_lookups):.2f}%")

    if lookup_error_types:
        logger.info("Error types (failed lookups):")
        for err, cnt in lookup_error_types.most_common():
            logger.info(f"  - {err}: {cnt:,} ({pct(cnt, total_lookups):.2f}% of all lookups)")

    logger.info(f"Latency P50/P95/P99: {percentile_str(durations, [50, 95, 99])}")
    logger.info(f"Attempted peers P50/P95: {percentile_str(attempted, [50, 95])}")
    logger.info(f"Successful peers P50/P95: {percentile_str(successful_peers, [50, 95])}")
    logger.info(f"Local success rank P50/P95: {percentile_str(success_rank, [50, 95])}")
    logger.info(f"Lookup score (best returned rank) P50/P95: {percentile_str(lookup_scores, [50, 95])}")

    closeness_scores = [x["closeness_score"] for x in parsed if x.get("closeness_score") is not None]
    if closeness_scores:
        logger.info("Closeness score:")
        logger.info(f"  P50 rank: {int(np.percentile(closeness_scores, 50))}")
        logger.info(f"  P95 rank: {int(np.percentile(closeness_scores, 95))}")

    return {
        "total_lookups": total_lookups,
        "success_rate": pct(success_count, total_lookups),
        "durations": durations,
        "attempted": attempted,
        "success_rank": success_rank,
        "lookup_scores": lookup_scores,
        "closeness_scores": closeness_scores
    }

class KadDHTAnalyzer(Analyzer):
    """
    Handles the analysis of KAD DHT and warmup logs from either local files or online data.
    """

    def with_warmup_check(self, bootstrap_pod: str = "bootstrap-0", *, on_fail: OnFail = "continue") -> Self:
        return self._with_parameterized_check(
            self.analyze_warmup,
            on_fail=on_fail,
            bootstrap_pod=bootstrap_pod
        )

    def with_dht_lookup_check(self, probe_pod: str = "probe-0", *, on_fail: OnFail = "continue") -> Self:
        return self._with_parameterized_check(
            self.analyze_lookups,
            on_fail=on_fail,
            probe_pod=probe_pod
        )

    def _get_bootstrap_start_time(self, bootstrap_pod: str) -> pd.Timestamp:
        extra_fields = self.data_puller.kwargs.get("extra_fields")
        tracer = KadDHTTracer().with_extra_fields(extra_fields).with_node_started_pattern()
        
        data = self.data_puller.get_pod_logs(tracer, bootstrap_pod)
        df = tracer.patterns[0].trace(data)[0]

        if df.empty:
            raise RuntimeError(
                f"No 'Node started' log found for {bootstrap_pod} in the configured time range."
            )

        return df["timestamp"].max()

    def analyze_warmup(self, bootstrap_pod: str) -> AnalysisResult:
        logger.info("=== Analyzing Warmup ===")
        t0 = self._get_bootstrap_start_time(bootstrap_pod)
        logger.info(f"Experiment start (bootstrap 'Node started'): {t0}")

        extra_fields = self.data_puller.kwargs.get("extra_fields")
        tracer = KadDHTTracer().with_extra_fields(extra_fields).with_warmup_pattern()
        
        stateful_sets = self.data_puller.kwargs.get("stateful_sets", [])
        nodes_per_statefulset = self.data_puller.kwargs.get("nodes_per_statefulset", [])

        dfs = self.data_puller.get_all_node_dataframes(tracer, stateful_sets, nodes_per_statefulset)

        bootstrap_dfs = [node_data["warmup"][0] for node_data in dfs]
        warmup_dfs = [node_data["warmup"][1] for node_data in dfs]

        bootstrap_df = pd.concat(bootstrap_dfs, ignore_index=True)
        warmup_df = pd.concat(warmup_dfs, ignore_index=True)

        if bootstrap_df.empty and warmup_df.empty:
            logger.info("No warmup events found in the given time range.")
            return AnalysisResult(name="warmup", intermediates={}, status="passed")

        # Discard events from previous experiments (anything before this run's t=0)
        if not bootstrap_df.empty:
            bootstrap_df = bootstrap_df[bootstrap_df["timestamp"] >= t0].copy()
        if not warmup_df.empty:
            warmup_df = warmup_df[warmup_df["timestamp"] >= t0].copy()

        if bootstrap_df.empty and warmup_df.empty:
            logger.info("No warmup events found after the bootstrap start time.")
            return AnalysisResult(name="warmup", intermediates={}, status="passed")

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
            logger.info(f"Connected to bootstrap — min: {b.min():.1f}s  median: {b.median():.1f}s  max: {b.max():.1f}s  ({len(b)} nodes)")
        if not warmup_df.empty:
            w = warmup_df["elapsed_s"]
            logger.info(f"Warmup complete       — min: {w.min():.1f}s  median: {w.median():.1f}s  max: {w.max():.1f}s  ({len(w)} nodes)")

        return AnalysisResult(
            name="warmup",
            intermediates={
                "t0": t0,
                "bootstrap_df": bootstrap_df,
                "warmup_df": warmup_df
            },
            status="passed"
        )

    def _extract_all_pids(self) -> List[str]:
        extra_fields = self.data_puller.kwargs.get("extra_fields")
        tracer = KadDHTTracer().with_extra_fields(extra_fields).with_peer_id_pattern()
        
        stateful_sets = self.data_puller.kwargs.get("stateful_sets", [])
        nodes_per_statefulset = self.data_puller.kwargs.get("nodes_per_statefulset", [])

        dfs = self.data_puller.get_all_node_dataframes(tracer, stateful_sets, nodes_per_statefulset)
        
        all_pids = []
        for node_data in dfs:
            df = node_data["peer_id"][0]
            if not df.empty and "peerId" in df.columns:
                all_pids.extend(df["peerId"].dropna().tolist())
                
        return list(set(all_pids))

    def analyze_lookups(self, probe_pod: str) -> AnalysisResult:
        logger.info("\n=== Analyzing Lookups ===")
        
        extra_fields = self.data_puller.kwargs.get("extra_fields")
        tracer = KadDHTTracer().with_extra_fields(extra_fields).with_kad_dht_pattern()
        
        data = self.data_puller.get_pod_logs(tracer, probe_pod)
        log_lines = data[0][0]

        if not log_lines:
            logger.info("No lookup events found.")
            return AnalysisResult(name="kad_dht_lookups", intermediates={}, status="passed")

        all_pids = self._extract_all_pids()
        parsed = [parse_row(row, all_pids) for row in log_lines]
        
        metrics = calculate_lookups_metrics(parsed)
        
        return AnalysisResult(
            name="kad_dht_lookups",
            intermediates=metrics,
            status="passed"
        )
