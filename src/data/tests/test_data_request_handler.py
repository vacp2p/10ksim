# Python Imports
import unittest
import pandas as pd

# Project Imports
from src.data.data_request_handler import DataRequestHandler


class TestDataRequestHandler(unittest.TestCase):

    def test_create_dataframe_from_request(self):
        raw_data = {
            'data': {
                'result': [
                    {
                        'metric': {
                            'instance': 'instance1',
                            'job': 'job1'
                        },
                        'values': [
                            ['1', 2],
                            ['2', 4]
                        ]
                    },
                    {
                        'metric': {
                            'instance': 'instance2',
                            'job': 'job2'
                        },
                        'values': [
                            ['1', 3],
                            ['2', 6]
                        ]
                    }
                ]
            }
        }
        expected_df_dict = {
            'Time': ['1970-01-01 00:00:01', '1970-01-01 00:00:02'],
            'job1_instance1': [2, 4],
            'job2_instance2': [3, 6]
        }
        # Convert dict to dataframe, keeping time column as datetime index
        expected_df = pd.DataFrame(expected_df_dict)
        expected_df['Time'] = pd.to_datetime(expected_df['Time'])
        expected_df.set_index('Time', inplace=True)

        drh = DataRequestHandler(raw_data)
        drh.create_dataframe_from_request('job-instance')
        self.assertIsNone(pd.testing.assert_frame_equal(drh.dataframe, expected_df))

    def test__extract_column_name_from_result(self):
        drh = DataRequestHandler({})
        pod_result = {
            'metric': {
                'instance': 'instance1',
                'job': 'job1'
            }
        }
        self.assertEqual(drh._extract_column_name_from_result('job-instance', pod_result), 'job1_instance1')

    def test__extract_column_name_from_result_multiple(self):
        drh = DataRequestHandler({})
        pod_result = {
            'metric': {
                'instance': 'instance1',
                'job': 'job1',
                'cluster': 'cluster1'
            }
        }
        self.assertEqual(drh._extract_column_name_from_result('job-instance-cluster', pod_result), 'job1_instance1_cluster1')

    def test__create_pod_df(self):
        drh = DataRequestHandler({})
        column_name = 'job1_instance1'
        values = [
            ['1', 2],
            ['2', 4]
        ]
        expected_df_dict = {
            'Time': ['1970-01-01 00:00:01', '1970-01-01 00:00:02'],
            'job1_instance1': [2, 4]
        }

        expected_df = pd.DataFrame(expected_df_dict)
        expected_df['Time'] = pd.to_datetime(expected_df['Time'])
        expected_df.set_index('Time', inplace=True)

        self.assertIsNone(pd.testing.assert_frame_equal(drh._create_pod_df(column_name, values), expected_df))

    def test__sort_dataframe_columns(self):
        drh = DataRequestHandler({})
        drh._dataframe = pd.DataFrame({
            'bootstrap-1_in': [1, 2],
            'bootstrap-3_in': [3, 4],
            'bootstrap-2_in': [5, 6],
        })
        drh._sort_dataframe_columns()
        self.assertEqual(drh.dataframe.columns.tolist(), ['bootstrap-1_in', 'bootstrap-2_in', 'bootstrap-3_in'])