import logging
from pathlib import Path
from typing import List, Optional, Self, Tuple

import pandas as pd
import seaborn as sns
from pydantic import BaseModel, NonNegativeInt
from result import Err, Ok, Result

# Project Imports
from src.analysis.mesh_analysis.analyzers.analyzer import AnalysisResult, Analyzer, OnFail
from src.analysis.mesh_analysis.readers.tracers.message_tracer import MessageTracer
from src.analysis.mesh_analysis.readers.tracers.nimlibp2p_tracer import Nimlibp2pTracer
from src.analysis.utils import file_utils, path_utils

logger = logging.getLogger(__name__)
sns.set_theme()


class MessageReliabilityResult(BaseModel):
    num_unique_messages: NonNegativeInt
    num_peers: NonNegativeInt
    all_in_same_shard: bool
    nodes_missing_messages: List[str]


class StatefulSetNodes(BaseModel):
    name: str
    expected: NonNegativeInt
    actual: NonNegativeInt


class MessageReliabilityAnalysis(BaseModel):
    ss_nodes: List[StatefulSetNodes]
    reliability_result: MessageReliabilityResult


class Nimlibp2pAnalyzer(Analyzer):
    """
    Handles the analysis of Nimlibp2p message reliability from either local log files or online data.

    The class ensures that every Nimlibp2p node received every expected message. It facilitates both local
    and online analysis of message reliability, merging and processing dataframes, and dumping results.
    In cases of missed messages, the class logs details and optionally dumps relevant node logs. It
    supports parallel processing to improve analysis efficiency.

    """

    msg_hash_key: str = "msgId"

    def with_ss_check(
        self,
        stateful_sets: List[str],
        expected_ss_nodes: List[NonNegativeInt],
        *,
        on_fail: OnFail = "continue",
    ) -> Self:
        return self._with_parameterized_check(
            self.check_ss_nodes,
            on_fail=on_fail,
            stateful_sets=stateful_sets,
            expected_ss_nodes=expected_ss_nodes,
        )

    def with_reliability_check(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[NonNegativeInt],
        expected_num_peers: NonNegativeInt,
        expected_num_messages: NonNegativeInt,
        *,
        on_fail: OnFail = "continue",
    ) -> Self:
        return self._with_parameterized_check(
            self.analyze_reliability,
            on_fail=on_fail,
            stateful_sets=stateful_sets,
            nodes_per_ss=nodes_per_ss,
            expected_num_peers=expected_num_peers,
            expected_num_messages=expected_num_messages,
            has_shards=False,
        )

    def check_ss_nodes(
        self,
        stateful_sets: List[str],
        expected_ss_nodes: List[NonNegativeInt],
    ) -> AnalysisResult:
        ss_nodes: List[StatefulSetNodes] = self._num_statefulset_nodes(
            stateful_sets, expected_ss_nodes
        )
        passed = all(map(lambda ss: ss.expected == ss.actual, ss_nodes))

        if not passed:
            error_message = f"Number of nodes in cluster does not match with provided data.\nStatefulSets: {ss_nodes}"
            logger.error(error_message)

        return AnalysisResult(
            name="num_ss_nodes",
            intermediates={
                "ss_nodes": ss_nodes,
                **({"failed": error_message} if not passed else {}),
            },
            status="passed" if passed else "failed",
        )

    def _num_statefulset_nodes(
        self,
        stateful_sets: List[str],
        expected_ss_nodes: List[NonNegativeInt],
    ) -> List[StatefulSetNodes]:
        num_nodes_per_ss = self.data_puller.get_number_nodes(stateful_sets)

        results = []
        for i, num_nodes in enumerate(num_nodes_per_ss):
            results.append(
                StatefulSetNodes(
                    name=stateful_sets[i],
                    expected=expected_ss_nodes[i],
                    actual=num_nodes,
                )
            )

        return results

    def reliability_tracer(self, extra_fields) -> MessageTracer:
        return (
            Nimlibp2pTracer()
            .with_extra_fields(extra_fields)
            .with_received_pattern_group()
            .with_sent_pattern_group()
        )

    def analyze_reliability(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[NonNegativeInt],
        expected_num_peers: NonNegativeInt,
        expected_num_messages: NonNegativeInt,
        has_shards: bool,
    ) -> AnalysisResult:
        # For local data puller, use "kubernetes.pod_name" as the header for file name.
        # For Victoria use "kubernetes.pod_name" and "kubernetes.pod_node_name".
        extra_fields = (
            ["kubernetes.pod_name"]
            if self.data_puller.is_local()
            else ["kubernetes.pod_name", "kubernetes.pod_node_name"]
        )
        tracer = self.reliability_tracer(extra_fields)

        reliability_result = self._analyze_reliability_cluster(
            stateful_sets, nodes_per_ss, tracer, has_shards
        )
        passed = (
            reliability_result.all_in_same_shard
            and reliability_result.num_peers == expected_num_peers
            and reliability_result.num_unique_messages == expected_num_messages
        )
        results_dict = reliability_result.model_dump()
        if not has_shards:
            del results_dict["all_in_same_shard"]
        return AnalysisResult(
            name="reliability",
            intermediates=results_dict,
            status="passed" if passed else "failed",
        )

    def _analyze_reliability_cluster(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[NonNegativeInt],
        tracer: MessageTracer,
        has_shards: bool,
    ) -> MessageReliabilityResult:
        dfs = self.data_puller.get_all_node_dataframes_new(tracer, stateful_sets, nodes_per_ss)
        # Strip suffix for local read.
        for dfs_dicts in dfs:
            for _key, df_list in dfs_dicts.items():
                for df in df_list:
                    df["kubernetes.pod_name"] = df["kubernetes.pod_name"].str.removesuffix(".log")

        dfs = self._merge_dfs(dfs, has_shards)
        self.adjust_dfs(dfs)
        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.warning(f"Issue dumping message summary. {result.err_value}")

        reliability_results = self._has_message_reliability_issues(
            "shard" if has_shards else None,
            self.msg_hash_key,
            "kubernetes.pod_name",
            dfs[0],
            dfs[1],
            self._dump_analysis_path,
        )

        if reliability_results.nodes_missing_messages:
            logger.info("Dumping logs from nodes with issues")
            self._dump_logs(reliability_results.nodes_missing_messages)

        return reliability_results

    def adjust_dfs(self, dfs: List[pd.DataFrame]):
        # We either had legacy lightpush requests xor lightpush requests.
        # Thus, dfs[0] is our received
        self.fill_unknown_in_received_df(dfs[0])

    def fill_unknown_in_received_df(self, df: pd.DataFrame):
        """Map from kubernetes.pod_name to receiver_peer_id
        for cases where my_peer_id was not included in sender (legacy lightpush requests)"""
        unknown_key = Nimlibp2pTracer.unknown_sender_str
        if "receiver_peer_id" in df.columns:
            pod_to_peer_map = (
                df.loc[df["receiver_peer_id"] != unknown_key]
                .drop_duplicates("kubernetes.pod_name")
                .set_index("kubernetes.pod_name")["receiver_peer_id"]
            )
            df.loc[df["receiver_peer_id"] == unknown_key, "receiver_peer_id"] = df.loc[
                df["receiver_peer_id"] == unknown_key, "kubernetes.pod_name"
            ].map(pod_to_peer_map)

    def _dump_dfs(self, dfs: List[pd.DataFrame]) -> Result:
        received = dfs[0].reset_index()
        received = received.astype(str)
        logger.info("Dumping received information")
        result = file_utils.dump_df_as_csv(
            received, self._dump_analysis_path / "summary" / "received.csv", False
        )
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        sent = dfs[1].reset_index()
        sent = sent.astype(str)
        logger.info("Dumping sent information")
        result = file_utils.dump_df_as_csv(
            sent, self._dump_analysis_path / "summary" / "sent.csv", False
        )
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        return Ok(None)

    def _merge_dfs(self, dfs: List[List[pd.DataFrame]], has_shard: bool) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")

        received_df = pd.concat(
            [pd.concat(group["received"], ignore_index=True) for group in dfs],
            ignore_index=True,
        )
        if has_shard:
            received_df = received_df.assign(
                shard=received_df["kubernetes.pod_name"].str.extract(r".*-(\d+)-").astype(int)
            )
        columns = [self.msg_hash_key, "timestamp"]
        if has_shard:
            columns = ["shard"] + columns
        received_df.set_index(columns, inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat(
            [pd.concat(group["sent"], ignore_index=True) for group in dfs],
            ignore_index=True,
        )
        if has_shard:
            sent_df = sent_df.assign(
                shard=sent_df["kubernetes.pod_name"].str.extract(r".*-(\d+)-").astype(int)
            )
        sent_df.set_index(columns, inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _has_message_reliability_issues(
        self,
        shard_identifier: Optional[str],
        msg_identifier: str,
        peer_identifier: str,
        received_df: pd.DataFrame,
        sent_df: pd.DataFrame,
        issue_dump_location: Path,
    ) -> MessageReliabilityResult:
        num_peers = len(received_df[peer_identifier].unique())
        logger.info(f"Nº of Peers: {num_peers}")
        unique_messages = len(received_df.index.get_level_values(self.msg_hash_key).unique())
        logger.info(f"Nº of unique messages: {unique_messages}")

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(
            shard_identifier, msg_identifier, peer_identifier, received_df
        )

        received_df = received_df.reset_index()
        has_shard_violations = False
        if shard_identifier is not None:
            shard_groups = received_df.groupby(self.msg_hash_key)[shard_identifier].nunique()
            shard_violations = shard_groups[shard_groups > 1]
            has_shard_violations = not shard_violations.empty

            if shard_violations.empty:
                logger.info(f"All {self.msg_hash_key} values appear in only one shard.")
            else:
                logger.warning(f"These {self.msg_hash_key} values appear in multiple shards:")
                logger.warning(shard_violations)

        if peers_missed_messages:
            msg_sent_data = self._check_if_msg_has_been_sent(
                peers_missed_messages, missed_messages, sent_df
            )
            for data in msg_sent_data:
                peer_id = data[0].split("*")[-1]
                logger.info(f"Peer {peer_id} message information dumped in {issue_dump_location}")
                match path_utils.prepare_path_for_file(
                    issue_dump_location / f"{data[0].split('*')[-1]}.csv"
                ):
                    case Ok(location_path):
                        data[1].to_csv(location_path)
                    case Err(err):
                        logger.error(err)
                        exit(1)

        return MessageReliabilityResult(
            all_in_same_shard=not has_shard_violations,
            num_unique_messages=unique_messages,
            num_peers=num_peers,
            nodes_missing_messages=peers_missed_messages,
        )

    def _get_peers_missed_messages(
        self,
        shard_identifier: Optional[str],
        msg_identifier: str,
        peer_identifier: str,
        df: pd.DataFrame,
    ) -> Tuple[List, List]:

        if shard_identifier is not None:
            all_peers_missed_messages = []
            all_missing_messages = []
            for shard, df_shard in df.groupby(level=shard_identifier):
                peers, missing = self._get_peers_missed_messages_for_shard(
                    shard, msg_identifier, peer_identifier, df_shard
                )
                all_peers_missed_messages.extend(peers)
                all_missing_messages.extend(missing)
            return all_peers_missed_messages, all_missing_messages
        else:
            return self._get_peers_missed_messages_for_shard(
                shard_identifier, msg_identifier, peer_identifier, df
            )

    def _get_peers_missed_messages_for_shard(
        self,
        shard: Optional[str],
        msg_identifier: str,
        peer_identifier: str,
        df: pd.DataFrame,
    ) -> Tuple[List, List]:
        all_peers_missed_messages = []
        all_missing_messages = []

        unique_messages = len(df.index.get_level_values(msg_identifier).unique())

        grouped = df.groupby([msg_identifier, peer_identifier]).size().reset_index(name="count")
        pivot_df = grouped.pivot_table(
            index=msg_identifier,
            columns=peer_identifier,
            values="count",
            fill_value=0,
        )

        peers_missed_msg = pivot_df.columns[pivot_df.sum() != unique_messages].to_list()
        missing_messages = pivot_df.index[pivot_df.eq(0).any(axis=1)].tolist()

        if not peers_missed_msg:
            logger.info(f"All peers received all messages for shard {shard}")
        else:
            logger.warning(f"Nodes missed messages on shard {shard}")
            logger.warning(f"Nodes who missed messages: {peers_missed_msg}")
            logger.warning(f"Missing messages: {missing_messages}")

            all_peers_missed_messages.extend(peers_missed_msg)
            all_missing_messages.extend(missing_messages)

            self._log_received_messages(pivot_df, unique_messages, df)

        return all_peers_missed_messages, all_missing_messages

    def _log_received_messages(
        self, df: pd.DataFrame, unique_messages: int, complete_df: pd.DataFrame
    ):
        column_sums = df.sum()
        filtered_sums = column_sums[column_sums != unique_messages]
        result_list = list(filtered_sums.items())
        for result in result_list:
            pod_name, count = result
            missing_hashes = df[df[pod_name] == 0].index.tolist()
            missing_hashes.extend(df[df[pod_name].isna()].index.tolist())
            pod_name = complete_df[complete_df["kubernetes.pod_name"] == result[0]][
                "receiver_peer_id"
            ].iloc[0][0]
            logger.warning(
                f"Node {result[0]} ({pod_name}) {result[1]}/{unique_messages}: {missing_hashes}"
            )

    def _check_if_msg_has_been_sent(
        self, peers: List, missed_messages: List, sent_df: pd.DataFrame
    ) -> List:
        messages_sent_to_peer = []
        for peer in peers:
            try:
                filtered_df = sent_df.loc[(slice(None), missed_messages), :]
                filtered_df = filtered_df[filtered_df["receiver_peer_id"] == peer]
                messages_sent_to_peer.append((peer, filtered_df))
            except KeyError as _:
                logger.warning(
                    f"Message {missed_messages} has not been sent to {peer} by any other node."
                )

        return messages_sent_to_peer
