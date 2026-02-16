# Python Imports
import unittest

# Project Imports
from src.metrics.scrape_utils import create_promql


class TestScrapeUtils(unittest.TestCase):

    def test_create_promql(self):
        address = "0.0.0.0:9090/api/"
        query = "bandwidth"
        start_scrape = "2024-03-12 16:24:00"
        finish_scrape = "2024-03-12 16:30:00"
        step = 60

        result = create_promql(address, query, start_scrape, finish_scrape, step)
        expected_result = (
            "0.0.0.0:9090/api/query_range?query=bandwidth&"
            "start=1710257040.0&"
            "end=1710257400.0&"
            "step=60"
        )

        self.assertEqual(expected_result, result)
