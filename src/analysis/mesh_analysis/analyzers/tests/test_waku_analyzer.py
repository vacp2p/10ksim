import base64
import json

import pandas as pd

from src.analysis.mesh_analysis.analyzers.waku.waku_analyzer import WakuAnalyzer


def _hash_pair(suffix: str):
    """A message hash in the two shapes: log form and store REST form."""
    raw = bytes.fromhex(suffix)
    return "0x" + raw.hex(), base64.b64encode(raw).decode("ascii")


def _write_archive(folder, name, encoded_hashes):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(encoded_hashes))


def _write_received(path, log_hashes):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"msg_hash": log_hashes}).to_csv(path, index=False)


def test_store_archive_check_reports_each_node(tmp_path, caplog):
    first_log, first_store = _hash_pair("aa" * 32)
    second_log, second_store = _hash_pair("bb" * 32)
    received = tmp_path / "summary" / "received.csv"
    # Duplicated because every receiving node logs the same message.
    _write_received(received, [first_log, second_log, first_log])

    archives = tmp_path / "store_messages"
    _write_archive(archives, "store-0-0", [first_store, second_store])
    _write_archive(archives, "store-0-1", [first_store])

    with caplog.at_level("INFO"):
        WakuAnalyzer().check_store_archives(archives, received_csv=received)

    assert "`store-0-0` holds all 2 messages" in caplog.text
    assert "`store-0-1` holds 1 of 2 messages" in caplog.text
    assert "Store nodes with a complete archive: 1 of 2" in caplog.text


def test_store_archive_check_without_dumps(tmp_path, caplog):
    received = tmp_path / "summary" / "received.csv"
    _write_received(received, ["0x" + "aa" * 32])

    with caplog.at_level("INFO"):
        WakuAnalyzer().check_store_archives(tmp_path / "store_messages", received_csv=received)

    assert "No store archive dumps found" in caplog.text
