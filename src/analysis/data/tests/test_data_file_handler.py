import logging

import pandas as pd

from src.analysis.data.data_file_handler import DataFileHandler


def _write_csv(path, rows=3, value=1.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    times = pd.to_datetime([f"2026-08-10 01:{m:02d}:00" for m in range(rows)])
    pd.DataFrame({"pod-0": [value] * rows}, index=times).rename_axis("Time").to_csv(path)


def _mean(folder):
    handler = DataFileHandler()
    handler.concat_dataframes_from_folders_as_mean([folder], 3)
    return handler.dataframe


def test_reads_the_csvs_a_scrape_wrote(tmp_path):
    _write_csv(tmp_path / "libp2p-in" / "quic.csv")
    assert not _mean(tmp_path / "libp2p-in").empty


def test_non_csv_files_are_left_alone(tmp_path):
    """The folder is discovered rather than named, so junk in it must not be read."""
    _write_csv(tmp_path / "libp2p-in" / "quic.csv")
    (tmp_path / "libp2p-in" / ".DS_Store").write_bytes(b"\x00\x01junk")
    (tmp_path / "libp2p-in" / "notes.txt").write_text("scratch")
    assert not _mean(tmp_path / "libp2p-in").empty


def test_a_scrape_taken_before_the_suffix_change_says_how_to_fix_it(tmp_path, caplog):
    """Those dumps read as an empty folder otherwise, and an empty plot looks like a result."""
    _write_csv(tmp_path / "libp2p-in" / "quic")
    with caplog.at_level(logging.ERROR):
        assert _mean(tmp_path / "libp2p-in").empty
    assert "no .csv suffix" in caplog.text
    assert "quic" in caplog.text
    assert "-exec mv" in caplog.text


def test_an_empty_folder_still_reports(tmp_path, caplog):
    (tmp_path / "libp2p-in").mkdir()
    with caplog.at_level(logging.ERROR):
        assert _mean(tmp_path / "libp2p-in").empty
    assert "holds no files" in caplog.text
