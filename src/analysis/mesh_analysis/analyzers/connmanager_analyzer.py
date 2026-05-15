import logging
from typing import List, Optional, Self

import pandas as pd

from src.analysis.mesh_analysis.analyzers.analyzer import AnalysisResult, Analyzer, OnFail
from src.analysis.mesh_analysis.readers.tracers.connmanager_tracer import ConnManagerTracer

logger = logging.getLogger(__name__)


class ConnManagerAnalyzer(Analyzer):
    def with_hub_analysis(
        self,
        hub_pod: str = "hub-0",
        grace_period_s: int = 0,
        protected_peer_ids: Optional[List[str]] = None,
        wave_sets: Optional[List[str]] = None,
        *,
        on_fail: OnFail = "continue",
    ) -> Self:
        return self._with_parameterized_check(
            self.analyze_hub,
            on_fail=on_fail,
            hub_pod=hub_pod,
            grace_period_s=grace_period_s,
            protected_peer_ids=protected_peer_ids,
            wave_sets=wave_sets,
        )

    def analyze_hub(
        self,
        hub_pod: str,
        grace_period_s: int = 0,
        protected_peer_ids: Optional[List[str]] = None,
        wave_sets: Optional[List[str]] = None,
    ) -> AnalysisResult:
        logger.info("=== Analyzing Connection Manager ===")

        extra_fields = self.data_puller.kwargs.get("extra_fields", [])

        tracer = (
            ConnManagerTracer()
            .with_extra_fields(extra_fields)
            .with_stored_muxer_pattern()
            .with_dropping_peer_pattern()
        )
        data = self.data_puller.get_pod_logs(tracer, hub_pod)
        traced = tracer.trace(data)
        muxer_df = traced["stored_muxer"][0]
        drop_df = traced["dropping_peer"][0]

        if muxer_df.empty:
            logger.warning("No connection events found.")
            return AnalysisResult(
                name="connmanager",
                intermediates={},
                status="passed",
            )

        summary = self._summarize(muxer_df, drop_df, grace_period_s, protected_peer_ids, wave_sets)

        return AnalysisResult(
            name="connmanager",
            intermediates={
                "conn_df": muxer_df,
                "drop_df": drop_df,
                **summary,
            },
            status="passed",
        )

    def _summarize(
        self,
        conn_df: pd.DataFrame,
        drop_df: pd.DataFrame,
        grace_period_s: int,
        protected_peer_ids: Optional[List[str]],
        wave_sets: Optional[List[str]] = None,
    ) -> dict:
        outbound_ids = set(conn_df[conn_df["direction"] == "Out"]["peer_id"])
        inbound_ids = set(conn_df[conn_df["direction"] == "In"]["peer_id"])
        dropped_ids = set(drop_df["peer_id"]) if not drop_df.empty else set()

        outbound_dropped = outbound_ids & dropped_ids
        inbound_dropped = inbound_ids & dropped_ids

        logger.info(f"Total connection events : {len(conn_df)}")
        logger.info(f"  Outbound (hub-dialed) : {len(outbound_ids)}")
        logger.info(f"  Inbound               : {len(inbound_ids)}")
        logger.info(f"Peers pruned            : {len(dropped_ids)}")
        if outbound_dropped:
            logger.warning(f"Outbound peers dropped  : {len(outbound_dropped)} << UNEXPECTED")
        else:
            logger.info(f"Outbound peers dropped  : 0 (scoring OK)")
        logger.info(f"Inbound peers dropped   : {len(inbound_dropped)}")

        if protected_peer_ids:
            protected_dropped = set(protected_peer_ids) & dropped_ids
            protected_survived = set(protected_peer_ids) - dropped_ids
            logger.info(f"Protected peers         : {len(protected_peer_ids)}")
            logger.info(f"  Survived              : {len(protected_survived)}")
            if protected_dropped:
                logger.warning(
                    f"  Dropped               : {len(protected_dropped)} << protection failed"
                )

        result = {
            "outbound_ids": outbound_ids,
            "inbound_ids": inbound_ids,
            "dropped_ids": dropped_ids,
            "outbound_dropped": outbound_dropped,
        }

        if grace_period_s > 0 and wave_sets:
            conn_labeled = self._label_waves(conn_df, wave_sets)
            result["conn_df_labeled"] = conn_labeled
        else:
            result["conn_df_labeled"] = conn_df

        return result

    def _label_waves(
        self, conn_df: pd.DataFrame, wave_sets: List[str]
    ) -> pd.DataFrame:
        extra_fields = self.data_puller.kwargs.get("extra_fields", [])
        peer_id_to_wave: dict[str, str] = {}

        for wave_name in wave_sets:
            tracer = (
                ConnManagerTracer()
                .with_extra_fields(extra_fields)
                .with_peer_started_pattern()
            )
            data = self.data_puller.get_pod_logs(tracer, f"{wave_name}-*")
            traced = tracer.trace(data)
            started_df = traced["peer_started"][0]
            if started_df.empty:
                continue
            for pid in started_df["peer_id"]:
                peer_id_to_wave[pid] = wave_name

        if not peer_id_to_wave:
            logger.warning("Could not resolve wave pod peer IDs; skipping wave labels")
            return conn_df

        conn_df = conn_df.copy()
        conn_df["wave"] = conn_df["peer_id"].map(peer_id_to_wave).fillna("unknown")
        labeled = conn_df["wave"].ne("unknown").sum()
        logger.info(f"Wave labeling: {labeled}/{len(conn_df)} events matched to {wave_sets}")
        return conn_df
