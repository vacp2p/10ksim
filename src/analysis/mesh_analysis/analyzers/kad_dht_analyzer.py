from typing import List
import pandas as pd

from src.analysis.mesh_analysis.analyzers.analyzer import Analyzer
from src.analysis.mesh_analysis.readers.tracers.nimlibp2p_tracer import Nimlibp2pTracer
from src.analysis.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.analysis.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis

class KadDHTAnalyzer(Analyzer):
    """
    Handles the extraction of KAD DHT and warmup logs from either local files or online data.
    """

    def get_bootstrap_start_time(self, bootstrap_pod: str = "bootstrap-0") -> pd.Timestamp:
        tracer = Nimlibp2pTracer(extra_fields=self._kwargs.get("extra_fields")).with_node_started_pattern()
        queries = ['"Node started"']
        reader_builder = VictoriaReaderBuilder(tracer=tracer, queries=queries, kwargs=self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        data = stack_analysis.get_pod_logs(bootstrap_pod)
        df = tracer.patterns[0].trace(data)[0]

        if df.empty:
            raise RuntimeError(
                f"No 'Node started' log found for {bootstrap_pod} in the configured time range."
            )

        return df["timestamp"].max()

    def check_warmup_times(self, n_jobs: int = 4) -> tuple:
        tracer = Nimlibp2pTracer(extra_fields=self._kwargs.get("extra_fields")).with_warmup_pattern()
        queries = ['"Connected to bootstrap" OR "Warmup complete"']
        reader_builder = VictoriaReaderBuilder(tracer=tracer, queries=queries, kwargs=self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        dfs = stack_analysis.get_all_node_dataframes(
            self._kwargs.get("stateful_sets", []),
            self._kwargs.get("nodes_per_statefulset", []),
            n_jobs
        )

        bootstrap_dfs = [node_data["warmup"][0] for node_data in dfs]
        warmup_dfs = [node_data["warmup"][1] for node_data in dfs]

        bootstrap_df = pd.concat(bootstrap_dfs, ignore_index=True)
        warmup_df = pd.concat(warmup_dfs, ignore_index=True)

        return bootstrap_df, warmup_df

    def check_kad_dht_result(self):
        tracer = Nimlibp2pTracer(extra_fields=self._kwargs.get("extra_fields")).with_kad_dht_pattern()
        queries = ["Lookup finished"]
        reader_builder = VictoriaReaderBuilder(tracer=tracer, queries=queries, kwargs=self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        data = stack_analysis.get_pod_logs("probe-0")

        log_lines = data[0][0]

        return log_lines

    def extract_all_pids(self, n_jobs: int = 4) -> List[str]:
        tracer = Nimlibp2pTracer(extra_fields=self._kwargs.get("extra_fields")).with_peer_id_pattern()
        queries = ['"Node started"']
        reader_builder = VictoriaReaderBuilder(tracer=tracer, queries=queries, kwargs=self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        dfs = stack_analysis.get_all_node_dataframes(
            self._kwargs.get("stateful_sets", []),
            self._kwargs.get("nodes_per_statefulset", []),
            n_jobs
        )
        
        all_pids = []
        for node_data in dfs:
            df = node_data["peer_id"][0]
            if not df.empty and "peerId" in df.columns:
                all_pids.extend(df["peerId"].dropna().tolist())
                
        return list(set(all_pids))
