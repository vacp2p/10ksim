# Python Imports
import os
import unittest
import numpy as np
import pandas as pd
from pathlib import Path
from result import Ok, Err
from unittest.mock import patch

# Project Imports
from src.data.data_file_handler import DataFileHandler


class TestDataFileHandler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.current_directory = os.path.dirname(os.path.abspath(__file__))

    def test_add_dataframes_from_folder_as_mean(self):
        dfh = DataFileHandler()
        folder = self.current_directory + '/test_folder_1'
        dfh.add_dataframes_from_folders_as_mean([folder])
        self.assertTrue(np.array_equal(dfh.dataframe['test1.csv'].values, np.array([2.0, 5.0])))
        self.assertTrue(np.array_equal(dfh.dataframe['test2.csv'].values, np.array([4.0, 20.0])))
        self.assertEqual(dfh.dataframe['class'].values[0], 'tests/test_folder_1')

    def test__add_files_as_mean(self):
        dfh = DataFileHandler()
        data_files_path = ['test1.csv', 'test2.csv', 'error']
        df = pd.DataFrame()
        location = Path(self.current_directory + '/test_folder_1')

        df = dfh._add_files_as_mean(df, data_files_path, location)
        self.assertTrue(np.array_equal(df['test1.csv'].values, np.array([2.0, 5.0])))
        self.assertTrue(np.array_equal(df['test2.csv'].values, np.array([4.0, 20.0])))
        self.assertEqual(df.shape, (2, 2))

    @patch('src.data.data_file_handler.DataFileHandler.add_data_from_file')
    def test__add_files_as_mean_mocked(self, mock_add_dataframe_from_file_as_mean):
        dfh = DataFileHandler()
        data_files_path = ['a', 'b']

        mock_add_dataframe_from_file_as_mean.side_effect = [Ok("Ok"), Err("Error")]

        df = pd.DataFrame()
        dfh._add_files_as_mean(df, data_files_path, Path("test"))
        self.assertEqual(mock_add_dataframe_from_file_as_mean.call_count, 2)

    @patch('src.data.data_file_handler.DataHandler.add_file_as_mean_to_df')
    def test_add_data_from_file(self, mock_add_file_as_mean_to_df):
        file_path = Path(os.path.join(self.current_directory, 'test_folder_1/test1.csv'))

        mock_add_file_as_mean_to_df.return_value = None
        df = pd.DataFrame()
        dfh = DataFileHandler()
        result = dfh.add_data_from_file(df, file_path)

        self.assertIsInstance(result, Ok)
        self.assertEqual(result.ok_value, None)

    @patch('src.data.data_file_handler.DataHandler.add_file_as_mean_to_df')
    def test_add_data_from_file_err(self, mock_add_file_as_mean_to_df):
        mock_add_file_as_mean_to_df.return_value = None
        df = pd.DataFrame()
        dfh = DataFileHandler()
        result = dfh.add_data_from_file(df, Path("testfail"))
        self.assertIsInstance(result, Err)
        self.assertEqual(result.err_value, "testfail cannot be dumped to memory.")
