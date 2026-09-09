import re

import pandas as pd

from src.analysis.mesh_analysis.readers.tracers.waku_tracer import WakuTracer


def mock_queries(data, tracer):
    """
    Build the same parsed_logs structure that VictoriaReader.make_queries() passes
    to MessageTracer.trace().

    Data is ordered to match tracer.patterns. Each inner list represents the rows
    returned by that pattern group's separate VictoriaLogs query.
    """
    if len(data) != len(tracer.patterns):
        raise ValueError(
            f"Expected logs for {len(tracer.patterns)} pattern groups, got {len(data)}"
        )

    results = []

    for pattern_group, log_lines in zip(tracer.patterns, data):
        query_results = [[] for _ in pattern_group.trace_pairs]

        for log_line in log_lines:
            for index, trace_pair in enumerate(pattern_group.trace_pairs):
                if trace_pair.regex is None:
                    query_results[index].append(list(log_line))
                    continue

                match = re.search(trace_pair.regex, log_line[0])
                if match:
                    query_results[index].append([*match.groups(), *log_line[1:]])

        results.append(query_results)

    return results


def test_relay_received_regex_matches_plain_message_text():
    tracer = WakuTracer().with_received_pattern_group(log_format="TEXT")

    line = (
        "received relay message my_peer_id=16U*GiNg1a "
        "msg_hash=0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583 "
        "from_peer_id=16U*wJXtuH receivedTime=1763643976019361536"
    )

    parsed_logs = mock_queries(
        [
            [(line,)],
            [],
            [],
        ],
        tracer,
    )
    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received_relay"][0]

    assert list(received_df.columns) == [
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


def test_relay_received_regex_matches_json_encoded_message_text():
    """
    This is still TEXT mode: the entire serialized JSON-looking message exists in
    _msg, so the tracer must extract values through the relay regex.
    """
    tracer = WakuTracer().with_received_pattern_group(log_format="TEXT")

    line = (
        '{"ts":"2026-07-20 21:09:12.918+00:00",'
        '"_msg":"received relay message",'
        '"topics":"waku relay",'
        '"tid":7,'
        '"file":"protocol.nim:221",'
        '"my_peer_id":"16U*JttkFq",'
        '"msg_hash":"0xe0a42cf351ada62465857c547d8bd4b101e59f27c3ac30098ad9cf58bf38ac5b",'
        '"msg_id":"5e204f6fdb5f...9183b433dd30",'
        '"from_peer_id":"16U*iyAikJ",'
        '"topic":"/waku/2/rs/0/0",'
        '"contentTopic":"/my-app/1/dst/proto",'
        '"receivedTime":1784581752918722048,'
        '"payloadSizeBytes":1000.0}'
    )

    parsed_logs = mock_queries(
        [
            [(line,)],
            [],
            [],
        ],
        tracer,
    )
    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received_relay"][0]

    assert received_df.loc[0, "receiver_peer_id"] == "16U*JttkFq"
    assert (
        received_df.loc[0, "msg_hash"]
        == "0xe0a42cf351ada62465857c547d8bd4b101e59f27c3ac30098ad9cf58bf38ac5b"
    )
    assert received_df.loc[0, "sender_peer_id"] == "16U*iyAikJ"
    assert received_df.loc[0, "timestamp"] == pd.Timestamp(1784581752918722048, unit="ns")
    assert pd.api.types.is_datetime64_ns_dtype(received_df["timestamp"])


def test_relay_received_json():
    tracer = WakuTracer().with_received_pattern_group(log_format="JSON")
    relay_group, _, _ = tracer.patterns
    (relay_pair,) = relay_group.trace_pairs

    assert relay_group.name == "received_relay"
    assert relay_group.fields == [
        "log.my_peer_id",
        "log.msg_hash",
        "log.from_peer_id",
        "log.receivedTime",
    ]
    assert relay_pair.regex is None

    message_hash = "0xe0a42cf351ada62465857c547d8bd4b101e59f27c3ac30098ad9cf58bf38ac5b"
    parsed_logs = mock_queries(
        [
            [
                (
                    "16U*JttkFq",
                    message_hash,
                    "16U*iyAikJ",
                    1784581752918722048,
                )
            ],
            [],
            [],
        ],
        tracer,
    )

    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received_relay"][0]

    assert list(received_df.columns) == [
        "receiver_peer_id",
        "msg_hash",
        "sender_peer_id",
        "timestamp",
    ]
    assert received_df.loc[0, "receiver_peer_id"] == "16U*JttkFq"
    assert received_df.loc[0, "msg_hash"] == message_hash
    assert received_df.loc[0, "sender_peer_id"] == "16U*iyAikJ"
    assert received_df.loc[0, "timestamp"] == pd.Timestamp(1784581752918722048, unit="ns")
    assert pd.api.types.is_datetime64_ns_dtype(received_df["timestamp"])


def test_legacy_lightpush_received_json():
    tracer = WakuTracer().with_received_pattern_group(log_format="JSON")
    _, _, legacy_group = tracer.patterns
    (legacy_pair,) = legacy_group.trace_pairs

    assert legacy_group.name == "received_legacy_lightpush"
    assert legacy_group.fields == [
        "log.peer_id",
        "log.msg_hash",
        "log.receivedTime",
    ]
    assert legacy_pair.regex is None

    message_hash = "0x1441e3e14e6f957d2a45332378cda900e066022412d6a1c47c95e587d82e6eb2"
    parsed_logs = mock_queries(
        [
            [],
            [],
            [
                (
                    "12D*YCde2H",
                    message_hash,
                    1763646635380167168,
                )
            ],
        ],
        tracer,
    )

    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received_legacy_lightpush"][0]

    assert received_df.loc[0, "receiver_peer_id"] == WakuTracer.unknown_sender_str
    assert received_df.loc[0, "sender_peer_id"] == "12D*YCde2H"
    assert received_df.loc[0, "msg_hash"] == message_hash
    assert received_df.loc[0, "timestamp"] == pd.Timestamp(1763646635380167168, unit="ns")
    assert pd.api.types.is_datetime64_ns_dtype(received_df["timestamp"])


def test_received_json_fields_are_passed_to_correct_converters():
    """
    This is JSON mode: VictoriaReader has already extracted values from the
    structured log.* fields, so no tracer regex should run.
    """
    tracer = WakuTracer().with_received_pattern_group(log_format="JSON")

    assert [group.name for group in tracer.patterns] == [
        "received_relay",
        "received_lightpush",
        "received_legacy_lightpush",
    ]
    assert [group.fields for group in tracer.patterns] == [
        [
            "log.my_peer_id",
            "log.msg_hash",
            "log.from_peer_id",
            "log.receivedTime",
        ],
        [
            "log.my_peer_id",
            "log.peer_id",
            "log.msg_hash",
            "log.receivedTime",
        ],
        [
            "log.peer_id",
            "log.msg_hash",
            "log.receivedTime",
        ],
    ]
    assert all(pair.regex is None for group in tracer.patterns for pair in group.trace_pairs)

    relay_hash = "0xe0a42cf351ada62465857c547d8bd4b101e59f27c3ac30098ad9cf58bf38ac5b"
    lightpush_hash = "0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583"
    legacy_hash = "0x1441e3e14e6f957d2a45332378cda900e066022412d6a1c47c95e587d82e6eb2"

    parsed_logs = mock_queries(
        [
            [
                (
                    "16U*JttkFq",
                    relay_hash,
                    "16U*iyAikJ",
                    1784581752918722048,
                )
            ],
            [
                (
                    "16U*GiNg1a",
                    "16U*wJXtuH",
                    lightpush_hash,
                    1763643976019361536,
                )
            ],
            [
                (
                    "12D*YCde2H",
                    legacy_hash,
                    1763646635380167168,
                )
            ],
        ],
        tracer,
    )

    dfs = tracer.trace(parsed_logs)

    relay_df = dfs["received_relay"][0]
    assert list(relay_df.columns) == [
        "receiver_peer_id",
        "msg_hash",
        "sender_peer_id",
        "timestamp",
    ]
    assert relay_df.loc[0, "receiver_peer_id"] == "16U*JttkFq"
    assert relay_df.loc[0, "msg_hash"] == relay_hash
    assert relay_df.loc[0, "sender_peer_id"] == "16U*iyAikJ"
    assert relay_df.loc[0, "timestamp"] == pd.Timestamp(1784581752918722048, unit="ns")

    lightpush_df = dfs["received_lightpush"][0]
    assert list(lightpush_df.columns) == [
        "receiver_peer_id",
        "sender_peer_id",
        "msg_hash",
        "timestamp",
    ]
    assert lightpush_df.loc[0, "receiver_peer_id"] == "16U*GiNg1a"
    assert lightpush_df.loc[0, "sender_peer_id"] == "16U*wJXtuH"
    assert lightpush_df.loc[0, "msg_hash"] == lightpush_hash
    assert lightpush_df.loc[0, "timestamp"] == pd.Timestamp(1763643976019361536, unit="ns")

    legacy_df = dfs["received_legacy_lightpush"][0]
    assert list(legacy_df.columns) == [
        "receiver_peer_id",
        "sender_peer_id",
        "msg_hash",
        "timestamp",
    ]
    assert legacy_df.loc[0, "receiver_peer_id"] == WakuTracer.unknown_sender_str
    assert legacy_df.loc[0, "sender_peer_id"] == "12D*YCde2H"
    assert legacy_df.loc[0, "msg_hash"] == legacy_hash
    assert legacy_df.loc[0, "timestamp"] == pd.Timestamp(1763646635380167168, unit="ns")

    for dataframe in (relay_df, lightpush_df, legacy_df):
        assert pd.api.types.is_datetime64_ns_dtype(dataframe["timestamp"])


def test_sent_json_fields_are_passed_to_converter_without_regex():
    tracer = WakuTracer().with_sent_pattern_group(log_format="JSON")

    sent_group, mix_sent_group = tracer.patterns
    group = sent_group
    (pair,) = group.trace_pairs

    assert group.fields == [
        "log.my_peer_id",
        "log.msg_hash",
        "log.to_peer_id",
        "log.sentTime",
    ]
    assert pair.regex is None

    message_hash = "0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583"
    parsed_logs = mock_queries(
        [
            [
                (
                    "16U*GiNg1a",
                    message_hash,
                    "16U*wJXtuH",
                    1763643976019361536,
                )
            ],
            [],
        ],
        tracer,
    )

    dfs = tracer.trace(parsed_logs)
    sent_df = dfs["sent"][0]

    assert list(sent_df.columns) == [
        "sender_peer_id",
        "msg_hash",
        "receiver_peer_id",
        "timestamp",
    ]
    assert sent_df.loc[0, "sender_peer_id"] == "16U*GiNg1a"
    assert sent_df.loc[0, "msg_hash"] == message_hash
    assert sent_df.loc[0, "receiver_peer_id"] == "16U*wJXtuH"
    assert sent_df.loc[0, "timestamp"] == pd.Timestamp(1763643976019361536, unit="ns")
    assert pd.api.types.is_datetime64_ns_dtype(sent_df["timestamp"])


def test_vlogs_separates_normal_and_mixnet_sent_messages():
    tracer = WakuTracer().with_sent_pattern_group(log_format="TEXT")
    sent_group, mix_sent_group = tracer.patterns

    assert sent_group.name == "sent"
    assert sent_group.query == '"sent relay message" AND NOT publishWithConn'

    assert mix_sent_group.name == "mix sent"
    assert mix_sent_group.query == '"sent relay message" AND publishWithConn'

    normal_hash = "0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583"
    mixnet_hash = "0xe0a42cf351ada62465857c547d8bd4b101e59f27c3ac30098ad9cf58bf38ac5b"

    normal_relay_line = (
        "sent relay message "
        "my_peer_id=16U*NormalSender "
        f"msg_hash={normal_hash} "
        "to_peer_id=16U*NormalReceiver "
        "sentTime=1763643976019361536"
    )
    mixnet_line = (
        "sent relay message publishWithConn "
        "my_peer_id=16U*MixnetSender "
        "peer_id=16U*MixnetReceiver "
        f"msg_hash={mixnet_hash} "
        "sentTime=1763646635380167168"
    )

    parsed_logs = mock_queries(
        [
            [(normal_relay_line,)],
            [(mixnet_line,)],
        ],
        tracer,
    )

    dfs = tracer.trace(parsed_logs)

    sent_df = dfs["sent"][0]
    assert len(sent_df) == 1
    assert sent_df.loc[0, "sender_peer_id"] == "16U*NormalSender"
    assert sent_df.loc[0, "msg_hash"] == normal_hash
    assert sent_df.loc[0, "receiver_peer_id"] == "16U*NormalReceiver"
    assert sent_df.loc[0, "timestamp"] == pd.Timestamp(1763643976019361536, unit="ns")

    mix_sent_df = dfs["mix sent"][0]
    assert len(mix_sent_df) == 1
    assert mix_sent_df.loc[0, "sender_peer_id"] == "16U*MixnetSender"
    assert mix_sent_df.loc[0, "receiver_peer_id"] == "16U*MixnetReceiver"
    assert mix_sent_df.loc[0, "msg_hash"] == mixnet_hash
    assert mix_sent_df.loc[0, "timestamp"] == pd.Timestamp(1763646635380167168, unit="ns")


def test_vlogs_separates_normal_and_mixnet_sent_json_messages():
    tracer = WakuTracer().with_sent_pattern_group(log_format="JSON")
    sent_group, mix_sent_group = tracer.patterns

    assert sent_group.fields == [
        "log.my_peer_id",
        "log.msg_hash",
        "log.to_peer_id",
        "log.sentTime",
    ]
    assert mix_sent_group.fields == [
        "log.my_peer_id",
        "log.peer_id",
        "log.msg_hash",
        "log.sentTime",
    ]

    assert sent_group.trace_pairs[0].regex is None
    assert mix_sent_group.trace_pairs[0].regex is None

    normal_hash = "0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583"
    mixnet_hash = "0xe0a42cf351ada62465857c547d8bd4b101e59f27c3ac30098ad9cf58bf38ac5b"

    parsed_logs = mock_queries(
        [
            [
                (
                    "16U*NormalSender",
                    normal_hash,
                    "16U*NormalReceiver",
                    1763643976019361536,
                )
            ],
            [
                (
                    "16U*MixnetSender",
                    "16U*MixnetReceiver",
                    mixnet_hash,
                    1763646635380167168,
                )
            ],
        ],
        tracer,
    )

    dfs = tracer.trace(parsed_logs)

    sent_df = dfs["sent"][0]
    assert len(sent_df) == 1
    assert sent_df.loc[0, "sender_peer_id"] == "16U*NormalSender"
    assert sent_df.loc[0, "msg_hash"] == normal_hash
    assert sent_df.loc[0, "receiver_peer_id"] == "16U*NormalReceiver"

    mix_sent_df = dfs["mix sent"][0]
    assert len(mix_sent_df) == 1
    assert mix_sent_df.loc[0, "sender_peer_id"] == "16U*MixnetSender"
    assert mix_sent_df.loc[0, "receiver_peer_id"] == "16U*MixnetReceiver"
    assert mix_sent_df.loc[0, "msg_hash"] == mixnet_hash
