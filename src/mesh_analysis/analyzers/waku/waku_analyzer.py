# Python Imports
import ast
import base64
import logging
import pandas as pd
import seaborn as sns
from pathlib import Path
from typing import List, Optional, Tuple
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.tracers.waku_tracer import WakuTracer
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
from src.utils import file_utils, log_utils, path_utils, list_utils

logger = logging.getLogger(__name__)
sns.set_theme()


class WakuAnalyzer:
    def __init__(self, dump_analysis_dir: str = None, local_folder_to_analyze: str = None, **kwargs):
        self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._kwargs = kwargs
        self._message_hashes = []
        self._stack: Optional[StackAnalysis] = None

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._dump_analysis_dir = Path(dump_analysis_dir) if dump_analysis_dir else None
        self._local_path_to_analyze = Path(local_folder_to_analyze) if local_folder_to_analyze else None
        result = path_utils.prepare_path_for_folder(self._dump_analysis_dir)
        if result.is_err():
            logger.error(result.err_value)
            exit(1)

    def _get_affected_node_pod(self, data_file: str) -> Result[str, str]:
        peer_id = data_file.split('.')[0]
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes.container_name:waku AND 'my_peer_id=16U*{peer_id}' AND _time:{self._timestamp} | limit 1"}}

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            pod_name = result.unwrap()['kubernetes.pod_name']
            logger.debug(f'Pod name for peer id {peer_id} is {pod_name}')
            return Ok(pod_name)

        return Err(f'Unable to obtain pod name from {peer_id}')

    def _get_affected_node_log(self, data_file: str) -> Result[Path, str]:
        result = self._get_affected_node_pod(data_file)
        if result.is_err():
            return Err(result.err_value)

        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": [{
                               "query": f"kubernetes.pod_name:{result.ok_value} AND _time:{self._timestamp} | sort by (_time)"}]}

        waku_tracer = WakuTracer()
        waku_tracer.with_wildcard_pattern()
        reader = VictoriaReader(victoria_config, waku_tracer)
        pod_log = reader.read()

        log_lines = [inner_list[0] for inner_list in pod_log[0]]
        log_name_path = self._dump_analysis_dir / f"{data_file.split('.')[0]}.log"
        with open(log_name_path, 'w') as file:
            for element in log_lines:
                file.write(f"{element}\n")

        return Ok(log_name_path)

    def _dump_information(self, data_files: List[str]):
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._get_affected_node_log, data_file): data_file for data_file in data_files}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    match result:
                        case Ok(log_path):
                            logger.info(f'{log_path} dumped')
                        case Err(_):
                            logger.warning(result.err_value)
                except Exception as e:
                    logger.error(f'Error retrieving logs for node {futures[future]}: {e}')

    def _analyze_reliability_local(self, n_jobs: int) :
        waku_tracer = WakuTracer(['file'])
        waku_tracer.with_received_group_pattern()
        waku_tracer.with_sent_pattern_group()

        reader = FileReader(self._local_path_to_analyze, waku_tracer, n_jobs)
        dfs = reader.read_logs()
        dfs = self._merge_dfs_local(dfs)

        received_df = dfs[0].assign(shard=0)
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = dfs[1].assign(shard=0)
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        result = self._dump_dfs([received_df, sent_df])
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        self._has_message_reliability_issues('shard', 'msg_hash', 'receiver_peer_id', received_df, sent_df,
                                                          self._dump_analysis_dir)

    def _merge_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        # TODO POD NAME should not be hardcoded
        logger.info("Merging and sorting information")

        received_df = pd.concat([pd.concat(group[0], ignore_index=True) for group in dfs], ignore_index=True)
        received_df = received_df.assign(shard=received_df['kubernetes.pod_name'].str.extract(r'.*-(\d+)-').astype(int))
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat([pd.concat(group[1], ignore_index=True) for group in dfs], ignore_index=True)
        sent_df = sent_df.assign(shard=sent_df['kubernetes.pod_name'].str.extract(r'.*-(\d+)-').astype(int))
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _merge_dfs_local(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        raise NotImplementedError
        # TODO POD NAME should not be hardcoded
        logger.info("Merging and sorting information")

        received_df = pd.concat(dfs[0], ignore_index=True)
        # TODO extract shard information from logs?
        received_df = received_df.assign(shard=received_df['kubernetes.pod_name'].str.extract(r'.*-(\d+)-').astype(int))
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat(dfs[1], ignore_index=True)
        sent_df = sent_df.assign(shard=sent_df['kubernetes.pod_name'].str.extract(r'.*-(\d+)-').astype(int))
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _dump_dfs(self, dfs: List[pd.DataFrame]) -> Result:
        received = dfs[0].reset_index()
        received = received.astype(str)
        logger.info("Dumping received information")
        result = file_utils.dump_df_as_csv(received, self._dump_analysis_dir / 'summary' / 'received.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        sent = dfs[1].reset_index()
        sent = sent.astype(str)
        logger.info("Dumping sent information")
        result = file_utils.dump_df_as_csv(sent, self._dump_analysis_dir / 'summary' / 'sent.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        return Ok(None)

    def _analyze_reliability_cluster(self, n_jobs: int):
        extract_fields = ['kubernetes.pod_name', 'kubernetes.pod_node_name']
        tracer = WakuTracer(msg_field='_msg', extra_fields=extract_fields)
        # TODO EL ORDEN DE COMO SE PONEN LOS WITHS REVIENTA EL CODIGO
        tracer.with_received_group_pattern()
        tracer.with_sent_pattern_group()

        queries = ['(received relay message OR  handling lightpush request)', 'sent relay message']
        reader_builder = VictoriaReaderBuilder(tracer, queries, **self._kwargs)

        self._stack = VaclabStackAnalysis(reader_builder, **self._kwargs)

        dfs = self._stack.get_node_logs(n_jobs, **self._kwargs)
        dfs = self._merge_dfs(dfs)

        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        has_issues = self._has_message_reliability_issues('shard', 'msg_hash', 'receiver_peer_id', dfs[0], dfs[1], self._dump_analysis_dir)
        if has_issues:
            match file_utils.get_files_from_folder_path(Path(self._dump_analysis_dir), extension="csv"):
                case Ok(data_files_names):
                    identifiers = [f"my_peer_id=16U*{file}" for file in data_files_names]
                    self._stack.dump_logs(identifiers, self._dump_analysis_dir)
                case Err(error):
                    logger.error(error)

    def analyze_reliability(self, n_jobs: int):
        if self._local_path_to_analyze is None:
            self._analyze_reliability_cluster(n_jobs)
        else:
            self._analyze_reliability_local(n_jobs)

    def _has_message_reliability_issues(self, shard_identifier: str, msg_identifier: str, peer_identifier: str,
                                        received_df: pd.DataFrame, sent_df: pd.DataFrame,
                                        issue_dump_location: Path) -> bool:
        logger.info(f'Nº of Peers: {len(received_df["receiver_peer_id"].unique())}')
        logger.info(f'Nº of unique messages: {len(received_df.index.get_level_values(1).unique())}')

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(shard_identifier, msg_identifier,
                                                                                 peer_identifier, received_df)

        received_df = received_df.reset_index()
        shard_groups = received_df.groupby('msg_hash')['shard'].nunique()
        violations = shard_groups[shard_groups > 1]

        if violations.empty:
            logger.info("All msg_hash values appear in only one shard.")
        else:
            logger.warning("These msg_hash values appear in multiple shards:")
            logger.warning(violations)

        if peers_missed_messages:
            msg_sent_data = self._check_if_msg_has_been_sent(peers_missed_messages, missed_messages, sent_df)
            # TODO check si realmente el nodo ha recibido el mensaje
            for data in msg_sent_data:
                peer_id = data[0].split('*')[-1]
                logger.info(f'Peer {peer_id} message information dumped in {issue_dump_location}')
                match path_utils.prepare_path_for_file(issue_dump_location / f"{data[0].split('*')[-1]}.csv"):
                    case Ok(location_path):
                        data[1].to_csv(location_path)
                    case Err(err):
                        logger.error(err)
                        exit(1)
            return True

        return False

    def _check_if_msg_has_been_sent(self, peers: List, missed_messages: List, sent_df: pd.DataFrame) -> List:
        messages_sent_to_peer = []
        for peer in peers:
            try:
                filtered_df = sent_df.loc[(slice(None), missed_messages), :]
                filtered_df = filtered_df[filtered_df['receiver_peer_id'] == peer]
                messages_sent_to_peer.append((peer, filtered_df))
            except KeyError as _:
                logger.warning(f'Message {missed_messages} has not ben sent to {peer} by any other node.')

        return messages_sent_to_peer

    def _get_peers_missed_messages(self, shard_identifier: str, msg_identifier: str, peer_identifier: str,
                                   df: pd.DataFrame) -> Tuple[List, List]:
        all_peers_missed_messages = []
        all_missing_messages = []

        for shard, df_shard in df.groupby(level=shard_identifier):
            unique_messages = len(df_shard.index.get_level_values(msg_identifier).unique())

            grouped = df_shard.groupby([msg_identifier, peer_identifier]).size().reset_index(name='count')
            pivot_df = grouped.pivot_table(index=msg_identifier, columns=peer_identifier, values='count', fill_value=0)

            peers_missed_msg = pivot_df.columns[pivot_df.sum() != unique_messages].to_list()
            missing_messages = pivot_df.index[pivot_df.eq(0).any(axis=1)].tolist()

            if not peers_missed_msg:
                logger.info(f'All peers received all messages for shard {shard}')
            else:
                logger.warning(f'Peers missed messages on shard {shard}')
                logger.warning(f'Peers who missed messages: {peers_missed_msg}')
                logger.warning(f'Missing messages: {missing_messages}')

                all_peers_missed_messages.extend(peers_missed_msg)
                all_missing_messages.extend(missing_messages)

                self._log_received_messages(pivot_df, unique_messages, df)

        return all_peers_missed_messages, all_missing_messages

    def _log_received_messages(self, df: pd.DataFrame, unique_messages: int, complete_df: pd.DataFrame):
        column_sums = df.sum()
        filtered_sums = column_sums[column_sums != unique_messages]
        result_list = list(filtered_sums.items())
        for result in result_list:
            peer_id, count = result
            missing_hashes = df[df[peer_id] == 0].index.tolist()
            missing_hashes.extend(df[df[peer_id].isna()].index.tolist())
            pod_name = complete_df[complete_df["receiver_peer_id"] == result[0]]["kubernetes.pod_name"][0][0]
            logger.warning(f'Peer {result[0]} ({pod_name}) {result[1]}/{unique_messages}: {missing_hashes}')

    def check_store_messages(self):
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes.pod_name:get-store-messages AND _time:{self._timestamp} | sort by (_time) desc | limit 1"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            messages_string = result.unwrap()['_msg']
            messages_list = ast.literal_eval(messages_string)
            messages_list = ['0x' + base64.b64decode(msg).hex() for msg in messages_list]
            logger.debug(f'Messages from store: {messages_list}')

            if len(self._message_hashes) != len(messages_list):
                logger.error('Number of messages does not match')
            elif set(self._message_hashes) == set(messages_list):
                logger.info('Messages from store match with received messages')
            else:
                logger.error('Messages from store does not match with received messages')
                logger.error(f'Received messages: {self._message_hashes}')
                logger.error(f'Store messages: {messages_list}')

            result = list_utils.dump_list_to_file(messages_list, self._dump_analysis_dir / 'store_messages.txt')
            if result.is_ok():
                logger.info(f'Messages from store saved in {result.ok_value}')

    def check_filter_messages(self):
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes.pod_name:get-filter-messages AND _time:{self._timestamp} | sort by (_time) desc | limit 1"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            messages_string = result.unwrap()['_msg']
            all_ok = ast.literal_eval(messages_string)
            if all_ok:
                logger.info("Messages from filter match in length.")
            else:
                logger.error("Messages from filter do not match.")

    def analyze_message_timestamps(self, time_difference_threshold: int):
        """
        Note that this function assumes that analyze_message_logs has been called, since timestamps will be checked
        from logs.
        """
        file_logs = file_utils.get_files_from_folder_path(self._local_path_to_analyze, extension='*.log')
        if file_logs.is_err():
            logger.error(file_logs.err_value)
            return

        logger.info(f'Analyzing timestamps from {len(file_logs.ok_value)} files')
        for file in file_logs.ok_value:
            logger.debug(f'Analyzing timestamps for {file}')
            time_jumps = log_utils.find_time_jumps(self._local_path_to_analyze / file, time_difference_threshold)

            for jump in time_jumps:
                logger.info(f'{file}: {jump[0]} to {jump[1]} -> {jump[2]}')
