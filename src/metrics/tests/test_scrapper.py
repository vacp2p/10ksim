# Python Imports
import datetime
import os
import unittest
import logging
from pathlib import Path
from unittest.mock import patch
from result import Ok, Err
import pandas as pd

# Project Imports
from src.metrics import scrapper

logger = logging.getLogger(__name__)


@patch('src.metrics.scrapper.get_query_data')
class TestScrapper(unittest.TestCase):

    @classmethod
    def tearDownClass(cls):
        os.rmdir('test_results')

    def test_query_and_dump_metrics_single(self, mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        data = {'result': [{'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]}]}

        mock_get_query_data.side_effect = [Ok(data)]

        test_scrapper.query_and_dump_metrics()

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5
        }

        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv('test_results/metric1.csv')
        # Convert data type since it is lost when reading from a file
        result['Unix Timestamp'] = pd.to_datetime(result['Unix Timestamp'])

        self.assertTrue(result.equals(expected_df))

        os.remove('test_results/metric1.csv')

    def test_query_and_dump_metrics_multiple_column(self, mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        data = {'result': [{'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]},
                           {'metric': {'instance': 'nodes-2'}, 'values': [[1, 6], [2, 6], [3, 6],
                                                                          [4, 6], [5, 6]]}
                           ]}

        mock_get_query_data.side_effect = [Ok(data)]

        test_scrapper.query_and_dump_metrics()

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5,
            'nodes-2': [6] * 5
        }
        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv('test_results/metric1.csv')
        # Convert data type since it is lost when reading from a file
        result['Unix Timestamp'] = pd.to_datetime(result['Unix Timestamp'])

        self.assertTrue(result.equals(expected_df))

        os.remove('test_results/metric1.csv')

    def test_query_and_dump_metrics_multiple_column_unordered(self, mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        data = {'result': [{'metric': {'instance': 'nodes-2'}, 'values': [[1, 6], [2, 6], [3, 6],
                                                                          [4, 6], [5, 6]]},
                           {'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]}
                           ]}

        mock_get_query_data.side_effect = [Ok(data)]

        test_scrapper.query_and_dump_metrics()

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5,
            'nodes-2': [6] * 5
        }
        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv('test_results/metric1.csv')
        # Convert data type since it is lost when reading from a file
        result['Unix Timestamp'] = pd.to_datetime(result['Unix Timestamp'])

        self.assertTrue(result.equals(expected_df))

        os.remove('test_results/metric1.csv')

    def test_query_and_dump_metrics_multiple_data(self, mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "test_scrape.yaml",
                                          "test_results/")

        data1 = {'result': [{'metric': {'instance': 'nodes-2'}, 'values': [[1, 6], [2, 6], [3, 6],
                                                                           [4, 6], [5, 6]]},
                            {'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                           [4, 5], [5, 5]]}
                            ]}
        data2 = {'result': [
            {'metric': {'instance': 'nodes-2', 'direction': 'in'},
             'values': [[1, 6], [2, 6], [3, 6],
                        [4, 6], [5, 6]]},
            {'metric': {'instance': 'nodes-1', 'direction': 'out'},
             'values': [[1, 5], [2, 5], [3, 5],
                        [4, 5], [5, 5]]}
        ]}

        mock_get_query_data.side_effect = [Ok(data1), Ok(data2)]

        test_scrapper.query_and_dump_metrics()

        expected_data_1 = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5,
            'nodes-2': [6] * 5
        }
        expected_df1 = pd.DataFrame(expected_data_1)

        expected_data_2 = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1_out': [5] * 5,
            'nodes-2_in': [6] * 5
        }
        expected_df2 = pd.DataFrame(expected_data_2)

        result1 = pd.read_csv('test_results/metric1.csv')
        # Convert data type since it is lost when reading from a file
        result1['Unix Timestamp'] = pd.to_datetime(result1['Unix Timestamp'])

        self.assertTrue(result1.equals(expected_df1))

        result2 = pd.read_csv('test_results/metric2[$__rate_interval]).csv')
        # Convert data type since it is lost when reading from a file
        result2['Unix Timestamp'] = pd.to_datetime(result2['Unix Timestamp'])

        self.assertTrue(result2.equals(expected_df2))

        os.remove('test_results/metric1.csv')
        os.remove('test_results/metric2[$__rate_interval]).csv')

    @patch('src.metrics.scrapper.Scrapper._dump_data')
    def test_query_and_dump_metrics_multiple_fail(self, mock_dump, mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "test_scrape.yaml",
                                          "test_results/")

        err1 = "Err1"
        err2 = "Err2"

        mock_get_query_data.side_effect = [Err(err1), Err(err2)]

        test_scrapper.query_and_dump_metrics()

        self.assertEqual(0, mock_dump.call_count)

    def test__set_query_config(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        test_scrapper._set_query_config()

        expected_config = {'scrape_config': {'until_hours_ago': 1, 'step': "60s",
                                             '$__rate_interval': '60s'},
                           'metrics_to_scrape': [{'metric1': 'instance'}]}

        self.assertEqual(expected_config, test_scrapper._query_config)

    @patch('src.metrics.scrape_utils._get_datetime_now')
    def test__create_query(self, mock_datetime_now, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        metric = "bandwidth"
        scrape_config = {'until_hours_ago': 1, 'step': "60s", '$__rate_interval': '60s'}

        return_value_first = datetime.datetime(2024, 2, 22, 11, 0, 0)
        return_value_second = datetime.datetime(2024, 2, 22, 12, 0, 0)
        mock_datetime_now.side_effect = [return_value_first, return_value_second]

        result = test_scrapper._create_query(metric, scrape_config)

        expected_result = ('http://myurl:9090/api/v1/query_range?query=bandwidth&start=1708592400'
                           '.0&end=1708599600.0&step=60s')

        self.assertEqual(expected_result, result)

    @patch('src.metrics.scrape_utils._get_datetime_now')
    def test__create_query_with_rate(self, mock_datetime_now, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        metric = "bandwidth[$__rate_interval]"
        scrape_config = {'until_hours_ago': 1, 'step': "60s", '$__rate_interval': '60s'}

        return_value_first = datetime.datetime(2024, 2, 22, 11, 0, 0)
        return_value_second = datetime.datetime(2024, 2, 22, 12, 0, 0)
        mock_datetime_now.side_effect = [return_value_first, return_value_second]

        result = test_scrapper._create_query(metric, scrape_config)

        expected_result = (
            'http://myurl:9090/api/v1/query_range?query=bandwidth[60s]&start=1708592400'
            '.0&end=1708599600.0&step=60s')

        self.assertEqual(expected_result, result)

    def test__dump_data(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("http://myurl:9090/api/v1/",
                                          "single_test_scrape.yaml",
                                          "test_results/")

        data = {'result': [{'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]}]}

        test_scrapper._dump_data('metric1', 'instance', data)

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5
        }
        expected_df = pd.DataFrame(expected_data)

        result = pd.read_csv('test_results/metric1.csv')
        # Convert data type since it is lost when reading from a file
        result['Unix Timestamp'] = pd.to_datetime(result['Unix Timestamp'])

        self.assertTrue(result.equals(expected_df))

        os.remove('test_results/metric1.csv')

    @patch('src.metrics.scrapper.Scrapper._prepare_path')
    def test__dump_data_err(self, mock_prepare_path, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "/")

        mock_prepare_path.return_value = Err("Error")
        data = {}

        with self.assertRaises(SystemExit) as cm:
            test_scrapper._dump_data('', '', data)

            self.assertEqual(cm.exception.code, 1)

    def test__prepare_path(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "test_path/")

        result = test_scrapper._prepare_path('metric1')

        self.assertEqual(Path('test_path/metric1.csv'), result.ok_value)

        os.rmdir('test_path/')

    def test__prepare_path_multiple(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "test_path_1/test_path_2")

        result = test_scrapper._prepare_path('metric1')

        self.assertEqual(Path('test_path_1/test_path_2/metric1.csv'), result.ok_value)

        os.rmdir('test_path_1/test_path_2/')
        os.rmdir('test_path_1')

    @patch('src.metrics.scrapper.Path.mkdir')
    def test__prepare_path_err(self, mock_mkdir, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "test_path_1/test_path_2")

        mock_mkdir.side_effect = OSError("Error")

        result = test_scrapper._prepare_path('metric1')

        self.assertIsInstance(result, Err)

    def test__create_dataframe_from_data(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        data = {'result': [{'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]}]}

        result = test_scrapper._create_dataframe_from_data(data, 'instance')

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5
        }
        expected_df = pd.DataFrame(expected_data)
        expected_df.set_index('Unix Timestamp', inplace=True)

        self.assertTrue(result.equals(expected_df))

    def test__create_dataframe_from_data_multiple(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        data = {'result': [{'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]},
                           {'metric': {'instance': 'nodes-2'}, 'values': [[1, 6], [2, 6], [3, 6],
                                                                          [4, 6], [5, 6]]}
                           ]}

        result = test_scrapper._create_dataframe_from_data(data, 'instance')

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5,
            'nodes-2': [6] * 5
        }
        expected_df = pd.DataFrame(expected_data)
        expected_df.set_index('Unix Timestamp', inplace=True)

        self.assertTrue(result.equals(expected_df))

    def test__create_dataframe_from_data_not_matching_times(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        data = {'result': [{'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [3, 5], [5, 5]]},
                           {'metric': {'instance': 'nodes-2'}, 'values': [[1, 6], [2, 6], [4, 6]]}
                           ]}

        result = test_scrapper._create_dataframe_from_data(data, 'instance')

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5, None, 5, None, 5],
            'nodes-2': [6, 6, None, 6, None]
        }
        expected_df = pd.DataFrame(expected_data)
        expected_df.set_index('Unix Timestamp', inplace=True)

        self.assertTrue(result.equals(expected_df))

    def test__sort_dataframe(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        data = {'result': [{'metric': {'instance': 'nodes-4'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]},
                           {'metric': {'instance': 'nodes-1'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]},
                           {'metric': {'instance': 'nodes-3'}, 'values': [[1, 5], [2, 5], [3, 5],
                                                                          [4, 5], [5, 5]]}
                           ]}

        df = test_scrapper._create_dataframe_from_data(data, 'instance')

        result = test_scrapper._sort_dataframe(df)

        expected_columns = ['nodes-1', 'nodes-3', 'nodes-4']

        self.assertEqual(expected_columns, result.columns.tolist())

    def test__create_pod_df(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        values = [[1, 5], [2, 5], [3, 5], [4, 5], [5, 5]]

        result = test_scrapper._create_pod_df('nodes-1', values)

        expected_data = {
            'Unix Timestamp': pd.to_datetime(
                ['1970-01-01 00:00:01', '1970-01-01 00:00:02', '1970-01-01 00:00:03',
                 '1970-01-01 00:00:04', '1970-01-01 00:00:05']),
            'nodes-1': [5] * 5
        }
        expected_df = pd.DataFrame(expected_data)
        expected_df.set_index('Unix Timestamp', inplace=True)

        self.assertTrue(result.equals(expected_df))

    def test__order(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        columns = ['nodes-4', 'nodes-1', 'nodes-3']

        result = test_scrapper._order(columns)

        expected_columns = ['nodes-1', 'nodes-3', 'nodes-4']

        self.assertEqual(expected_columns, result)

    def test__order_bootstrap(self, _mock_get_query_data):
        test_scrapper = scrapper.Scrapper("", "single_test_scrape.yaml", "")

        columns = ['nodes-4', 'nodes-1', 'nodes-3', 'bootstrap-2']

        result = test_scrapper._order(columns)

        expected_columns = ['bootstrap-2', 'nodes-1', 'nodes-3', 'nodes-4']

        self.assertEqual(expected_columns, result)