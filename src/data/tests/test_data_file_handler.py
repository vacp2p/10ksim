# Python Imports
import os
import unittest
import numpy as np
from pathlib import Path
from result import Ok, Err
from unittest.mock import patch

# Project Imports
from src.data.data_file_handler import DataFileHandler


class TestDataFileHandler(unittest.TestCase):

    def setUp(self):
        self.current_directory = os.path.dirname(os.path.abspath(__file__))

    def test_add_dataframes_from_folder_as_mean(self):
        dfh = DataFileHandler()
        folder = self.current_directory + '/test_folder_1'
        result = dfh.add_dataframes_from_folders_as_mean(folder)
        self.assertIsInstance(result, Ok)
        self.assertEqual(result.ok_value, folder)
        self.assertTrue(np.array_equal(dfh.dataframe['test1.csv'].values, np.array([2.0, 5.0])))
        self.assertTrue(np.array_equal(dfh.dataframe['test2.csv'].values, np.array([4.0, 20.0])))
        self.assertEqual(dfh.dataframe['class'].values[0], 'tests/test_folder_1')

    def test__add_files_as_mean(self):
        dfh = DataFileHandler()
        data_files_path = ['test1.csv', 'test2.csv', 'error']

        location = Path(self.current_directory + '/test_folder_1')

        dfh._add_files_as_mean(data_files_path, location)
        self.assertTrue(np.array_equal(dfh.dataframe['test1.csv'].values, np.array([2.0, 5.0])))
        self.assertTrue(np.array_equal(dfh.dataframe['test2.csv'].values, np.array([4.0, 20.0])))
        self.assertEqual(dfh.dataframe.shape, (2, 2))

    @patch('src.data.data_file_handler.DataFileHandler.add_dataframe_from_file_as_mean')
    def test__add_files_as_mean_mocked(self, mock_add_dataframe_from_file_as_mean):
        dfh = DataFileHandler()
        data_files_path = ['a', 'b']

        mock_add_dataframe_from_file_as_mean.side_effect = [Ok("Ok"), Err("Error")]

        dfh._add_files_as_mean(data_files_path, Path("test"))
        self.assertEqual(mock_add_dataframe_from_file_as_mean.call_count, 2)

    @patch('src.data.data_file_handler.DataFileHandler._dump_mean_df')
    def test_add_dataframe_from_file_as_mean(self, mock_dump_mean_df):
        file_path = Path(os.path.join(self.current_directory, 'test_folder_1/test1.csv'))

        mock_dump_mean_df.return_value = None

        dfh = DataFileHandler()
        result = dfh.add_data_from_file(file_path)
        self.assertIsInstance(result, Ok)
        self.assertEqual(result.ok_value, file_path)

    @patch('src.data.data_file_handler.DataFileHandler._dump_mean_df')
    def test_add_dataframe_from_file_as_mean_err(self, mock_dump_mean_df):
        mock_dump_mean_df.return_value = None

        dfh = DataFileHandler()
        result = dfh.add_data_from_file(Path("testfail"))
        self.assertIsInstance(result, Err)
        self.assertEqual(result.err_value, "testfail cannot be dumped to memory.")

    def test__dump_mean_df(self):
        dfh = DataFileHandler()
        file_path = Path(os.path.join(self.current_directory, 'test_folder_1/test1.csv'))
        dfh.add_file_as_mean_to_df(file_path)
        self.assertEqual(dfh.dataframe.columns, ['test1.csv'])
        self.assertTrue(np.array_equal(dfh.dataframe['test1.csv'].values, np.array([2.0, 5.0])))

    def test__dump_mean_df_with_data(self):
        dfh = DataFileHandler()
        file_path_1 = Path(os.path.join(self.current_directory, 'test_folder_1/test1.csv'))
        file_path_2 = Path(os.path.join(self.current_directory, 'test_folder_1/test2.csv'))
        dfh.add_file_as_mean_to_df(file_path_1)
        dfh.add_file_as_mean_to_df(file_path_2)
        self.assertTrue(np.array_equal(dfh.dataframe['test1.csv'].values, np.array([2.0, 5.0])))
        self.assertTrue(np.array_equal(dfh.dataframe['test2.csv'].values, np.array([4.0, 20.0])))





