import re

import pandas as pd

from src.analysis.mesh_analysis.readers.tracers.waku_tracer import WakuTracer


def mock_queries(data, tracer):
    results = [[] for _ in tracer.patterns]
    for i, pattern_group in enumerate(tracer.patterns):
        query_results = [[] for _ in pattern_group.trace_pairs]
        for log_line in data:
            for j, trace_pair in enumerate(pattern_group.trace_pairs):
                pattern = trace_pair.regex
                match = re.search(pattern, log_line[0])
                if match:
                    match_as_list = list(match.groups())
                    match_as_list.extend(log_line[1:])
                    query_results[j].append(match_as_list)
            results[i].extend(query_results)
    return results


def test_received_regex_matches_text():
    tracer = WakuTracer().with_received_pattern_group()

    line = (
        "received relay message my_peer_id=16U*GiNg1a "
        "msg_hash=0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583 "
        "from_peer_id=16U*wJXtuH receivedTime=1763643976019361536"
    )

    parsed_logs = mock_queries([[line]], tracer)
    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received"][0]

    assert list(received_df.columns[:4]) == [
        "receiver_peer_id",
        "msg_hash",
        "sender_peer_id",
        "timestamp",
    ]
    assert received_df.loc[0, "receiver_peer_id"] == "16U*GiNg1a"
    assert (
        received_df.loc[0, "msg_hash"]
        == "0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583"
    )
    assert received_df.loc[0, "sender_peer_id"] == "16U*wJXtuH"
    assert received_df.loc[0, "timestamp"] == pd.Timestamp(1763643976019361536, unit="ns")
    assert pd.api.types.is_datetime64_ns_dtype(received_df["timestamp"])


def test_received_regex_matches_json():
    tracer = WakuTracer().with_received_pattern_group()

    line = (
        '{"lvl":"DBG",'
        '"ts":2026-07-16 15:10:00.145+00:00,'
        '"msg":"received relay message",'
        '"topics":"waku relay",'
        '"tid":7,'
        '"file":"protocol.nim:221",'
        '"my_peer_id":"16U*S6zwhq",'
        '"msg_hash":"0x4d19ab4d7deebcd5c1935d7c27caab678566dbb14f3bf7858d09d466e7c79af7",'
        '"msg_id":"b9cfa467b62a...67128d31aecc",'
        '"from_peer_id":"16U*74x9yd",'
        '"topic":"/waku/2/rs/0/0",'
        '"contentTopic":"/my-app/1/dst/proto",'
        '"receivedTime":1784214600145432320,'
        '"payloadSizeBytes":1000.0}'
    )

    parsed_logs = mock_queries([[line]], tracer)
    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received"][0]

    assert list(received_df.columns[:4]) == [
        "receiver_peer_id",
        "msg_hash",
        "sender_peer_id",
        "timestamp",
    ]
    assert received_df.loc[0, "receiver_peer_id"] == "16U*S6zwhq"
    assert (
        received_df.loc[0, "msg_hash"]
        == "0x4d19ab4d7deebcd5c1935d7c27caab678566dbb14f3bf7858d09d466e7c79af7"
    )
    assert received_df.loc[0, "sender_peer_id"] == "16U*74x9yd"
    assert received_df.loc[0, "timestamp"] == pd.Timestamp(1784214600145432320, unit="ns")
    assert pd.api.types.is_datetime64_ns_dtype(received_df["timestamp"])
