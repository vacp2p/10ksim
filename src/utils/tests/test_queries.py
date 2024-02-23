# Python Imports
import unittest
import requests.exceptions
from unittest.mock import patch, MagicMock

# Project Imports
from src.utils.queries import get_query_data


@patch('src.utils.queries.requests.get')
class TestQueries(unittest.TestCase):

    def test_get_query_data_correct(self, mock_requests_get: MagicMock):
        mock_requests_get.return_value.ok = True
        mock_requests_get.return_value.json.return_value = {'data': 'foo'}

        result = get_query_data('https://foo/bar/1')

        self.assertEqual(result.ok_value, 'foo')

    def test_get_query_data_timeout(self, mock_requests_get: MagicMock):
        mock_requests_get.side_effect = requests.exceptions.Timeout

        result = get_query_data('https://foo/bar/1')

        self.assertEqual(result.err_value, 'Timeout error.')

    def test_get_query_data_error(self, mock_requests_get: MagicMock):
        mock_requests_get.return_value.ok = False
        mock_requests_get.return_value.status_code = 404
        mock_requests_get.return_value.content = 'bar'

        result = get_query_data('https://foo/bar/1')

        self.assertEqual(result.err_value, 'Error in query. Status code 404. bar')
