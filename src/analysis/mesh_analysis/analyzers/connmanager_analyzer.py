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
        *,
        on_fail: OnFail = "continue",
    ) -> Self:
        return self._with_parameterized_check(
            self.analyze_hub,
            on_fail=on_fail,
            hub_pod=hub_pod,
            grace_period_s=grace_period_s,
            protected_peer_ids=protected_peer_ids,
        )

    def analyze_hub(
        self,
        hub_pod: str,
        grace_period_s: int = 0,
        protected_peer_ids: Optional[List[str]] = None,
    ) -> AnalysisResult:
        logger.info("=== Analyzing Connection Manager ===")

        extra_fields = self.data_puller.kwargs.get("extra_fields", [])

        muxer_tracer = (
            ConnManagerTracer().with_extra_fields(extra_fields).with_stored_muxer_pattern()
        )
        muxer_data = self.data_puller.get_pod_logs(muxer_tracer, hub_pod)
        muxer_df = muxer_tracer.trace(muxer_data)["stored_muxer"][0]

        drop_tracer = (
            ConnManagerTracer().with_extra_fields(extra_fields).with_dropping_peer_pattern()
        )
        drop_data = self.data_puller.get_pod_logs(drop_tracer, hub_pod)
        drop_df = drop_tracer.trace(drop_data)["dropping_peer"][0]

        if muxer_df.empty:
            logger.warning("No connection events found.")
            return AnalysisResult(
                name="connmanager",
                intermediates={},
                status="passed",
            )

        summary = self._summarize(muxer_df, drop_df, grace_period_s, protected_peer_ids)

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

        if grace_period_s > 0:
            conn_labeled = self._label_waves(conn_df, grace_period_s)
            result["conn_df_labeled"] = conn_labeled
        else:
            result["conn_df_labeled"] = conn_df

        return result

    @staticmethod
    def _label_waves(conn_df: pd.DataFrame, grace_period_s: int) -> pd.DataFrame:
        if conn_df.empty or "peers" not in conn_df.columns:
            return conn_df
        conn_df = conn_df.copy()
        conn_df["wave"] = "wave1"
        idx = conn_df.index[len(conn_df) // 2 :]
        conn_df.loc[idx, "wave"] = "wave2"
        return conn_df
