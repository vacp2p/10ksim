# topics="libp2p gossipsub" tid=1 file=gossipsub.nim:486 msg_hash=0xaca84f9bc3bf5543c9d9ff0a300d46cc4f164459eea2a476efbbabd265816f69 msg_id=5e17e0fc6df4...29a9d6d6be2f sender_peer_id=16U*2HzxRU

# open folder from simulation, and get all log files.
# with composition, use Waku adapter
# create dataframe with a timestamped index
# for each logfile
    # save in the dataframe
        # TIMESTAMP | MSG_ID | SENDER | RECEIVER |


import re
import pandas as pd
import multiprocessing
from functools import reduce
from pathlib import Path

from src.utils import file_utils


class Tracer:

    def __init__(self):
        self._folder = "../../test/log_test/"

    def read_files(self):
        files_result = file_utils.get_files_from_folder_path(Path(self._folder))

        num_processes = multiprocessing.cpu_count()
        with multiprocessing.Pool(processes=1) as pool:
            id_results = pool.map(self.get_peer_id, files_result.ok_value)
            data_results = pool.map(self.read_file, files_result.ok_value)

        return id_results, data_results

    def read_file(self, file):
        result = {file: []}
        pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) .* msg_hash=([a-fA-F0-9x]+) .* sender_peer_id=([A-Za-z0-9]+)$')
        with open(Path(self._folder+file)) as log_file:
            for line in log_file:
                match = pattern.match(line)
                if match:
                # Timestamp, msg_hash, sender_peer
                    result[file].append([match.group(1), match.group(2), match.group(3)])

        return result

    def get_peer_id(self, file):
        pattern = r'.* Announcing addresses .*\[([^]]+)\]$'
        with open(Path(self._folder + file)) as log_file:
            for line in log_file:
                match = re.search(pattern, line)
                if match:
                    peer_id = match.group(1)
                    peer_id = peer_id.split('/')[-1]
                    return {file: peer_id}


if __name__ == '__main__':

    test = Tracer()
    id_results, data_results = test.read_files()
    id_results_merged = dict(reduce(lambda d1, d2: {**d1, **d2}, id_results))
    data_results_merged = dict(reduce(lambda d1, d2: {**d1, **d2}, data_results))

    test = None

    for log_key, entry in data_results_merged.items():
        if len(entry) > 0:
            test2 = pd.DataFrame(entry, columns=['timestamp', 'msg_hash', 'sender_peer_id'])
            test2['recevier_peer_id'] = id_results_merged[log_key]
            test = pd.concat([test, test2])

    test['timestamp'] = pd.to_datetime(test['timestamp'])
    test.set_index(['timestamp', 'msg_hash'], inplace=True)




