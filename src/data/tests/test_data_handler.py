# Python Imports
import os
import unittest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import patch

# Project Imports
from src.data.data_handler import DataHandler


class TestDataHandler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.current_directory = os.path.dirname(os.path.abspath(__file__))

    def test_prepare_dataframe_for_boxplot(self):
        """This is just making use of the melt method from pandas. But as it is quite confusing
        sometimes, this is a good example of how to use it, and why it is very suited for a
        boxplot.
        The idea is to create a dataframe with the following structure:
        A B C
        1 3 test
        2 4 test
        And then melt it to have a dataframe with the following structure:
        variable value class
        A 1 test
        A 2 test
        B 3 test
        B 4 test
        In this way, we can plot a boxplot with seaborn, where the x-axis is the variable, the y-axis
        is the value, and we can separate the boxplot by the class.
        In a more specific example, we can easily plot variables like bandwidth, where the class
        can be waku-v25, waku-v26. Allowing us to compare in a single plot, the different
        experiments.
        """
        data = {'in': [1, 2, 3, 4, 5],
                'out': [6, 7, 8, 9, 10],
                'class': ['testv1', 'testv1', 'testv2', 'testv2', 'testv2']}
        df = pd.DataFrame(data)

        prepared_df = DataHandler.prepare_dataframe_for_boxplot(df, 'class')

        self.assertEqual(prepared_df['class'].tolist(), ['testv1', 'testv1', 'testv2', 'testv2', 'testv2', 'testv1', 'testv1', 'testv2', 'testv2', 'testv2', ])
        self.assertEqual(prepared_df['variable'].tolist(), ['in', 'in', 'in', 'in', 'in', 'out', 'out', 'out', 'out', 'out'])
        self.assertEqual(prepared_df['value'].tolist(), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    def test_add_file_as_mean_to_df(self):
        df = pd.DataFrame()
        dh = DataHandler()
        file_path = Path(os.path.join(self.current_directory, 'resources/test_folder_1/test1.csv'))
        df = dh.add_file_as_mean_to_df(df, file_path)
        self.assertEqual(df.columns, ['test1.csv'])
        self.assertTrue(np.array_equal(df['test1.csv'].values, np.array([2.0, 5.0])))

    def test_add_file_as_mean_to_df_with_data(self):
        df = pd.DataFrame()
        dh = DataHandler()
        file_path_1 = Path(os.path.join(self.current_directory, 'resources/test_folder_1/test1.csv'))
        file_path_2 = Path(os.path.join(self.current_directory, 'resources/test_folder_1/test2.csv'))
        df = dh.add_file_as_mean_to_df(df, file_path_1)
        df = dh.add_file_as_mean_to_df(df, file_path_2)
        self.assertTrue(np.array_equal(df['test1.csv'].values, np.array([2.0, 5.0])))
        self.assertTrue(np.array_equal(df['test2.csv'].values, np.array([4.0, 20.0])))

    def test_dataframe(self):
        data_handler = DataHandler()
        self.assertIsNone(data_handler.dataframe)

    def test_dump_dataframe(self):
        file_path = os.path.join(self.current_directory, 'test.csv')

        data_handler = DataHandler()
        data_handler._dataframe = pd.DataFrame({'A': [1, 2, 3, 4, 5],
                                                'B': [6, 7, 8, 9, 10],
                                                'C': ['test', 'test', 'test', 'test', 'test']})
        data_handler.dump_dataframe(file_path)
        result = pd.read_csv(file_path, index_col=0)
        self.assertTrue(data_handler.dataframe.equals(result))
        os.remove(file_path)

    @patch('src.utils.path.prepare_path')
    def test_dump_dataframe_error(self, mock_prepare_path):
        file_path = os.path.join(self.current_directory, 'test.csv')

        mock_prepare_path.return_value.is_err.return_value = True
        mock_prepare_path.return_value.err_value = 'error'

        dh = DataHandler()
        dh._dataframe = pd.DataFrame()

        with self.assertRaises(SystemExit) as cm:
            dh.dump_dataframe(file_path)































