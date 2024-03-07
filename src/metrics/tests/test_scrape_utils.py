# Python Imports
import unittest
import datetime
from unittest.mock import patch, MagicMock

# Project Imports
from src.metrics.scrape_utils import create_promql


class TestScrapeUtils(unittest.TestCase):

    @patch('src.metrics.scrape_utils._get_datetime_now')
    def test_create_promql(self, mock_datetime_now: MagicMock):
        address = "0.0.0.0:9090/api/"
        query = "bandwidth"
        hours_passed = 1
        step = 60

        return_value_first = datetime.datetime(2024, 2, 22, 11, 0, 0)
        return_value_second = datetime.datetime(2024, 2, 22, 12, 0, 0)
        mock_datetime_now.side_effect = [return_value_first, return_value_second]

        result = create_promql(address, query, hours_passed, step)
        expected_result = ("0.0.0.0:9090/api/query_range?query=bandwidth&start=1708592400.0&end"
                           "=1708599600.0&step=60")

        self.assertEqual(expected_result, result)
