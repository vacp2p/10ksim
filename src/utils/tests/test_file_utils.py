# Python Imports
import os
import unittest
from result import Ok
from pathlib import Path

# Project Imports
from src.utils import file_utils


class TestFileUtils(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.current_directory = os.path.dirname(os.path.abspath(__file__))

    def test_read_yaml_file(self):
        test_file = os.path.join(self.current_directory, 'resources/test.yaml')
        result = file_utils.read_yaml_file(test_file)
        expected_result = {'test': 'test'}
        self.assertEqual(result, expected_result)

    def test_get_files_from_folder_path(self):
        test_folder = os.path.join(self.current_directory, 'resources')
        result = file_utils.get_files_from_folder_path(Path(test_folder))
        expected_result = ['empty.yaml', 'test.yaml']
        self.assertTrue(result.is_ok())
        self.assertEqual(result.ok_value, expected_result)
        self.assertIsInstance(result, Ok)

    def test_get_files_from_folder_path_error(self):
        test_folder = os.path.join(self.current_directory, 'resources', 'not_exist')
        result = file_utils.get_files_from_folder_path(Path(test_folder))
        self.assertTrue(result.is_err())
        self.assertEqual(f"{Path(test_folder)} does not exist.", result.err_value)
