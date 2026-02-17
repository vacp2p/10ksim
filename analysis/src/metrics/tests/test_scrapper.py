# Python Imports
import logging
import os
import shutil
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
from result import Err, Ok

# Project Imports
from src.metrics import scrapper

logger = logging.getLogger(__name__)


@patch("src.metrics.scrape_utils.get_query_data")
class TestScrapper(unittest.TestCase):

    def setUp(self):
        self.current_directory = os.path.dirname(os.path.abspath(__file__))

    def test_query_and_dump_metrics_single(self, mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        data = {
            "data": {
                "result": [
                    {
                        "metric": {"instance": "nodes-1"},
                        "values": [[1, 5], [2, 5], [3, 5], [4, 5], [5, 5]],
                    }
                ]
            }
        }

        mock_get_query_data.side_effect = [Ok(data)]

        test_scrapper.query_and_dump_metrics()

        expected_data = {
            "Time": pd.to_datetime(
                [
                    "1970-01-01 00:00:01",
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                    "1970-01-01 00:00:04",
                    "1970-01-01 00:00:05",
                ]
            ),
            "nodes-1": [5] * 5,
        }

        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv("test_results/libp2p-peers/test_single")
        # Convert data type since it is lost when reading from a file
        result["Time"] = pd.to_datetime(result["Time"])

        self.assertTrue(result.equals(expected_df))

        shutil.rmtree("test_results")

    def test_query_and_dump_metrics_multiple_column(self, mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        data = {
            "data": {
                "result": [
                    {
                        "metric": {"instance": "nodes-1"},
                        "values": [[1, 5], [2, 5], [3, 5], [4, 5], [5, 5]],
                    },
                    {
                        "metric": {"instance": "nodes-2"},
                        "values": [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6]],
                    },
                ]
            }
        }

        mock_get_query_data.side_effect = [Ok(data)]

        test_scrapper.query_and_dump_metrics()

        expected_data = {
            "Time": pd.to_datetime(
                [
                    "1970-01-01 00:00:01",
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                    "1970-01-01 00:00:04",
                    "1970-01-01 00:00:05",
                ]
            ),
            "nodes-1": [5] * 5,
            "nodes-2": [6] * 5,
        }
        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv("test_results/libp2p-peers/test_single")
        # Convert data type since it is lost when reading from a file
        result["Time"] = pd.to_datetime(result["Time"])

        self.assertTrue(result.equals(expected_df))

        shutil.rmtree("test_results")

    def test_query_and_dump_metrics_multiple_column_unordered(self, mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        data = {
            "data": {
                "result": [
                    {
                        "metric": {"instance": "nodes-2"},
                        "values": [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6]],
                    },
                    {
                        "metric": {"instance": "nodes-1"},
                        "values": [[1, 5], [2, 5], [3, 5], [4, 5], [5, 5]],
                    },
                ]
            }
        }

        mock_get_query_data.side_effect = [Ok(data)]

        test_scrapper.query_and_dump_metrics()

        expected_data = {
            "Time": pd.to_datetime(
                [
                    "1970-01-01 00:00:01",
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                    "1970-01-01 00:00:04",
                    "1970-01-01 00:00:05",
                ]
            ),
            "nodes-1": [5] * 5,
            "nodes-2": [6] * 5,
        }
        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv("test_results/libp2p-peers/test_single")
        # Convert data type since it is lost when reading from a file
        result["Time"] = pd.to_datetime(result["Time"])

        self.assertTrue(result.equals(expected_df))

        shutil.rmtree("test_results")

    def test_query_and_dump_metrics_multiple_data(self, mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        data1 = {
            "data": {
                "result": [
                    {
                        "metric": {"instance": "nodes-2"},
                        "values": [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6]],
                    },
                    {
                        "metric": {"instance": "nodes-1"},
                        "values": [[1, 5], [2, 5], [3, 5], [4, 5], [5, 5]],
                    },
                ]
            }
        }
        data2 = {
            "data": {
                "result": [
                    {
                        "metric": {"instance": "nodes-2", "direction": "in"},
                        "values": [[1, 6], [2, 6], [3, 6], [4, 6], [5, 6]],
                    },
                    {
                        "metric": {"instance": "nodes-1", "direction": "out"},
                        "values": [[1, 5], [2, 5], [3, 5], [4, 5], [5, 5]],
                    },
                ]
            }
        }

        mock_get_query_data.side_effect = [Ok(data1), Ok(data2)]

        test_scrapper.query_and_dump_metrics()

        expected_data_1 = {
            "Time": pd.to_datetime(
                [
                    "1970-01-01 00:00:01",
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                    "1970-01-01 00:00:04",
                    "1970-01-01 00:00:05",
                ]
            ),
            "nodes-1_out": [5] * 5,
            "nodes-2_in": [6] * 5,
        }
        expected_df1 = pd.DataFrame(expected_data_1)

        expected_data_2 = {
            "Time": pd.to_datetime(
                [
                    "1970-01-01 00:00:01",
                    "1970-01-01 00:00:02",
                    "1970-01-01 00:00:03",
                    "1970-01-01 00:00:04",
                    "1970-01-01 00:00:05",
                ]
            ),
            "nodes-1_out": [5] * 5,
            "nodes-2_in": [6] * 5,
        }
        expected_df2 = pd.DataFrame(expected_data_2)

        result1 = pd.read_csv("test_results/libp2p-peers/test_scrape")
        # Convert data type since it is lost when reading from a file
        result1["Time"] = pd.to_datetime(result1["Time"])

        self.assertTrue(result1.equals(expected_df1))

        result2 = pd.read_csv("test_results/libp2p-peers/test_scrape")
        # Convert data type since it is lost when reading from a file
        result2["Time"] = pd.to_datetime(result2["Time"])

        self.assertTrue(result2.equals(expected_df2))

        shutil.rmtree("test_results")

    @patch("src.metrics.scrapper.Scrapper._dump_data")
    def test_query_and_dump_metrics_multiple_fail(
        self, mock_dump: MagicMock, mock_get_query_data: MagicMock
    ):
        file_path = os.path.join(self.current_directory, "test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        err1 = "Err1"
        err2 = "Err2"

        mock_get_query_data.side_effect = [Err(err1), Err(err2)]

        test_scrapper.query_and_dump_metrics()

        self.assertEqual(0, mock_dump.call_count)

    def test__dump_data(self, _mock_get_query_data: MagicMock):
        with patch("src.metrics.scrapper.DataRequestHandler") as mock_data_handler:
            file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
            test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

            test_scrapper._dump_data("metric1", "instance", {}, "test_path/")

            mock_data_handler.assert_called_once()
            mock_data_handler.return_value.create_dataframe_from_request.assert_called_once()
            mock_data_handler.return_value.dump_dataframe.assert_called_once()

    def test__set_query_config(self, _mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        test_scrapper._set_query_config()

        expected_config = {
            "scrape_config": {
                "start_scrape": "2024-03-12 16:24:00",
                "finish_scrape": "2024-03-12 16:30:00",
                "step": "60s",
                "$__rate_interval": "60s",
                "dump_location": "test_results/",
                "simulation_name": "test_single",
            },
            "metrics_to_scrape": {
                "metric1": {
                    "query": "test-query",
                    "extract_field": "instance",
                    "folder_name": "libp2p-peers/",
                }
            },
        }

        self.assertEqual(expected_config, test_scrapper._query_config)

    def test__create_query(self, _mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        metric = "bandwidth"
        scrape_config = {
            "start_scrape": "2024-03-12 16:24:00",
            "finish_scrape": "2024-03-12 16:30:00",
            "step": "60s",
            "$__rate_interval": "60s",
        }

        result = test_scrapper._create_query(metric, scrape_config)

        expected_result = (
            "http://myurl:9090/api/v1/query_range?query=bandwidth&"
            "start=1710257040.0&end=1710257400.0&step=60s"
        )

        self.assertEqual(expected_result, result)

    def test__create_query_with_rate(self, _mock_get_query_data: MagicMock):
        file_path = os.path.join(self.current_directory, "single_test_scrape.yaml")
        test_scrapper = scrapper.Scrapper(None, "http://myurl:9090/api/v1/", file_path)

        metric = "bandwidth[$__rate_interval]"
        scrape_config = {
            "start_scrape": "2024-03-12 16:24:00",
            "finish_scrape": "2024-03-12 16:30:00",
            "step": "60s",
            "$__rate_interval": "60s",
        }

        result = test_scrapper._create_query(metric, scrape_config)

        expected_result = (
            "http://myurl:9090/api/v1/query_range?query=bandwidth[60s]&"
            "start=1710257040.0&end=1710257400.0&step=60s"
        )

        self.assertEqual(expected_result, result)
