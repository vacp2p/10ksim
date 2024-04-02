# Python Imports
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

# Project Imports
from src.utils import path


class TestPathUtils(unittest.TestCase):

    def test_prepare_path(self):
        test_path = 'test_folder/test_file'
        result_path = Path(test_path)
        result = path.prepare_path(test_path)
        self.assertTrue(result.is_ok())
        self.assertEqual(result_path, result.ok_value)
        shutil.rmtree('test_folder')

    @patch('pathlib.Path.mkdir')
    def test_prepare_path_oserror(self, mock_path_mkdir):
        mock_path_mkdir.side_effect = OSError
        test_path = 'test_folder/test_file'
        result = path.prepare_path(test_path)
        self.assertTrue(result.is_err())
        self.assertEqual('Error creating test_folder. ', result.err_value)
