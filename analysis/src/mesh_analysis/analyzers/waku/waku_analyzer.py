# Python Imports
from functools import partial
import ast
import base64
import json
import logging
import traceback
import pandas as pd
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt
import seaborn as sns
from pathlib import Path
from typing import Callable, ClassVar, Dict, List, Literal, Self, Tuple, Optional, Type
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.analyzers.waku.analyzer import AnalysisResult, AnalysisStep, Analyzer, OnFail
from src.mesh_analysis.analyzers.waku.data_puller import DataPuller
from src.mesh_analysis.stacks.file_stack_analysis import FileStack
from src.mesh_analysis.readers.reader import Reader
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.mesh_analysis.readers.builders.victoria_reader_builder import (
    VictoriaReaderBuilder,
)
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.tracers.waku_tracer import (
    NewTracer,
    NewWakuTracer,
    WakuTracer,
)
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
from src.utils import file_utils, list_utils, path_utils

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


class NewWakuAnalyzer(Analyzer):

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

    def analyze_reliability(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[NonNegativeInt],
        expected_num_peers: NonNegativeInt,
        expected_num_messages: NonNegativeInt,
    ) -> AnalysisResult:
        reliability_result = self._analyze_reliability_cluster(
            stateful_sets, nodes_per_ss
        )
        passed = (
            reliability_result.all_in_same_shard
            and reliability_result.num_peers == expected_num_peers
            and reliability_result.num_unique_messages == expected_num_messages
        )
        return AnalysisResult(
            name="reliability",
            intermediates=reliability_result.model_dump(),
            status="passed" if passed else "failed",
        )

    def _analyze_reliability_cluster(
        self,
        stateful_sets: List[str],
        nodes_per_ss: List[NonNegativeInt],
    ) -> MessageReliabilityResult:
        # For local data puller, use "kubernetes.pod_name" as the header for file name.
        # For Victoria use "kubernetes.pod_name" and "kubernetes.pod_node_name".
        extra_fields = (
            ["kubernetes.pod_name"]
            if self.data_puller.is_local()
            else ["kubernetes.pod_name", "kubernetes.pod_node_name"]
        )

        tracer = (
            NewWakuTracer()
            .with_received_pattern_group()
            .with_sent_pattern_group()
            .with_extra_fields(extra_fields)
        )
        dfs = self.data_puller.get_all_node_dataframes_new(
            tracer, stateful_sets, nodes_per_ss
        )

        dfs = self._merge_dfs(dfs)

        try:
            result = self._dump_dfs(dfs)
        except:
            logger.warning(f"Issue dumping message summary. {result.err_value}")

        reliability_results = self._has_message_reliability_issues(
            "shard",
            "msg_hash",
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
        unknown_key = WakuTracer.unknown_sender_str
        # Mapping from kubernetes.pod_name to receiver_peer_id
        # for cases where my_peer_id was not included in sender (legacy lightpush requests)
        pod_to_peer_map = (
            df.loc[df["receiver_peer_id"] != unknown_key]
            .drop_duplicates("kubernetes.pod_name")
            .set_index("kubernetes.pod_name")["receiver_peer_id"]
        )
        df.loc[df["receiver_peer_id"] == unknown_key, "receiver_peer_id"] = df.loc[
            df["receiver_peer_id"] == unknown_key, "kubernetes.pod_name"
        ].map(pod_to_peer_map)

    def _dump_dfs(self, dfs: List[pd.DataFrame]) -> Result:
        self.adjust_dfs(dfs)

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

    def _merge_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")

        received_df = pd.concat(
            [pd.concat(group["received"], ignore_index=True) for group in dfs],
            ignore_index=True,
        )
        received_df = received_df.assign(
            shard=received_df["kubernetes.pod_name"]
            .str.extract(r".*-(\d+)-")
            .astype(int)
        )
        received_df.set_index(["shard", "msg_hash", "timestamp"], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat(
            [pd.concat(group["sent"], ignore_index=True) for group in dfs],
            ignore_index=True,
        )
        sent_df = sent_df.assign(
            shard=sent_df["kubernetes.pod_name"].str.extract(r".*-(\d+)-").astype(int)
        )
        sent_df.set_index(["shard", "msg_hash", "timestamp"], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _has_message_reliability_issues(
        self,
        shard_identifier: str,
        msg_identifier: str,
        peer_identifier: str,
        received_df: pd.DataFrame,
        sent_df: pd.DataFrame,
        issue_dump_location: Path,
    ) -> MessageReliabilityResult:
        num_peers = len(received_df["receiver_peer_id"].unique())
        logger.info(f"Nº of Peers: {num_peers}")
        unique_messages = len(received_df.index.get_level_values(1).unique())
        logger.info(f"Nº of unique messages: {unique_messages}")

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(
            shard_identifier, msg_identifier, peer_identifier, received_df
        )

        received_df = received_df.reset_index()
        shard_groups = received_df.groupby("msg_hash")["shard"].nunique()
        violations = shard_groups[shard_groups > 1]

        if violations.empty:
            logger.info("All msg_hash values appear in only one shard.")
        else:
            logger.warning("These msg_hash values appear in multiple shards:")
            logger.warning(violations)

        if peers_missed_messages:
            msg_sent_data = self._check_if_msg_has_been_sent(
                peers_missed_messages, missed_messages, sent_df
            )
            for data in msg_sent_data:
                peer_id = data[0].split("*")[-1]
                logger.info(
                    f"Peer {peer_id} message information dumped in {issue_dump_location}"
                )
                match path_utils.prepare_path_for_file(
                    issue_dump_location / f"{data[0].split('*')[-1]}.csv"
                ):
                    case Ok(location_path):
                        data[1].to_csv(location_path)
                    case Err(err):
                        logger.error(err)
                        exit(1)

        return MessageReliabilityResult(
            all_in_same_shard=violations.empty,
            num_unique_messages=unique_messages,
            num_peers=num_peers,
            nodes_missing_messages=peers_missed_messages,
        )

    def _merge_dfs_local(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        """
        TODO currently shard information is picked in the pod's name during the experiment. If you are working with
        local logs, make sure that each node has it's own log file, named like <node>-<shard>-<node_index>.
        """
        logger.info("Merging and sorting information")

        received_df = pd.concat(dfs[0], ignore_index=True)
        received_df = received_df.assign(
            shard=received_df["file"].str.extract(r".*-(\d+)-").astype(int)
        )
        received_df.set_index(["shard", "msg_hash", "timestamp"], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat(dfs[1], ignore_index=True)
        sent_df = sent_df.assign(
            shard=sent_df["file"].str.extract(r".*-(\d+)-").astype(int)
        )
        sent_df.set_index(["shard", "msg_hash", "timestamp"], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _get_peers_missed_messages(
        self,
        shard_identifier: str,
        msg_identifier: str,
        peer_identifier: str,
        df: pd.DataFrame,
    ) -> Tuple[List, List]:
        all_peers_missed_messages = []
        all_missing_messages = []

        for shard, df_shard in df.groupby(level=shard_identifier):
            unique_messages = len(
                df_shard.index.get_level_values(msg_identifier).unique()
            )

            grouped = (
                df_shard.groupby([msg_identifier, peer_identifier])
                .size()
                .reset_index(name="count")
            )
            pivot_df = grouped.pivot_table(
                index=msg_identifier,
                columns=peer_identifier,
                values="count",
                fill_value=0,
            )

            peers_missed_msg = pivot_df.columns[
                pivot_df.sum() != unique_messages
            ].to_list()
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

    def check_store_messages(self):
        """
        It checks that the messages obtained by get-store-messages pod are the same messages detected in
        analyze_reliability. This is used to detect if the store nodes can retrieve all messages.
        It has to be used after analyze_reliability, and this function only makes sense if there were store nodes
        in the experiment.
        :return:
        """
        waku_tracer = WakuTracer().with_wildcard_pattern()

        self.stack.get_pod_logs(pod_identifier="get-store-messages", query="*")

        reader = VictoriaReaderBuilder(waku_tracer, "*", **self._kwargs)
        stack = VaclabStackAnalysis(reader, **self._kwargs)
        data = stack.get_pod_logs("get-store-messages")

        log_list = data[0][0]  # We will always have 1 pattern group with 1 pattern
        messages_list = ast.literal_eval(
            log_list[-1]
        )  # Last line in get-store-messages
        messages_list = ["0x" + base64.b64decode(msg).hex() for msg in messages_list]
        logger.debug(f"Messages from store: {messages_list}")

        if len(self._message_hashes) != len(messages_list):
            logger.error("Number of messages does not match")
        elif set(self._message_hashes) == set(messages_list):
            logger.info("Messages from store match with received messages")
        else:
            logger.error("Messages from store does not match with received messages")
            logger.error(f"Received messages: {self._message_hashes}")
            logger.error(f"Store messages: {messages_list}")

        result = list_utils.dump_list_to_file(
            messages_list, self._dump_analysis_path / "store_messages.txt"
        )
        if result.is_ok():
            logger.info(f"Messages from store saved in {result.ok_value}")

    def check_filter_messages(self):
        """
        It checks that the messages obtained by get-filter-messages pod are the same messages detected in
        analyze_reliability. This is used to detect if the filter nodes received all messages.
        It has to be used after analyze_reliability, and this function only makes sense if there were filter nodes
        in the experiment.
        :return:
        """
        waku_tracer = WakuTracer().with_wildcard_pattern()
        reader = VictoriaReaderBuilder(waku_tracer, "*", **self._kwargs)
        stack = VaclabStackAnalysis(reader, **self._kwargs)
        data = stack.get_pod_logs("get-filter-messages")

        log_list = data[0][0]  # We will always have 1 pattern group with 1 pattern
        all_ok_boolean = ast.literal_eval(
            log_list[-1]
        )  # Last line in get-filter-messages

        all_ok = ast.literal_eval(all_ok_boolean)
        if all_ok:
            logger.info("Messages from filter match in length.")
        else:
            logger.error("Messages from filter do not match.")
