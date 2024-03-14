# Python Imports
import unittest
import pandas as pd
from unittest.mock import MagicMock

# Project Imports
from src.plotting.plotter import Plotter


class TestPlotter(unittest.TestCase):

    def test_create_plots(self):
        config = {"plot1": {}, "plot2": {}}
        plotter = Plotter(config)

        plotter._create_plot = MagicMock()
        plotter.create_plots()
        self.assertEqual(plotter._create_plot.call_count, 2)

    def test__create_plot(self):
        plotter = Plotter({})
        plotter._create_subplot_paths_group = MagicMock()
        plotter._insert_data_in_axs = MagicMock()
        plotter._save_plot = MagicMock()

        plotter._create_plot("", {'data': [0]})
        self.assertEqual(plotter._create_subplot_paths_group.call_count, 1)
        self.assertEqual(plotter._insert_data_in_axs.call_count, 1)
        self.assertEqual(plotter._save_plot.call_count, 1)

    def test__insert_data_in_axs(self):
        plotter = Plotter({})
        plotter._create_subplot_df = MagicMock(return_value=pd.DataFrame({"class": ["class1", "class2"], "value": [1, 2]}))
        plotter._add_subplot_df_to_axs = MagicMock()
        plotter._create_subplot_paths_group = MagicMock()
        plotter._insert_data_in_axs(["test", "test"], None)

        self.assertEqual(plotter._create_subplot_df.call_count, 2)
        self.assertEqual(plotter._add_subplot_df_to_axs.call_count, 2)

    def test__save_plot(self):
        plotter = Plotter({})
        plt = MagicMock()
        plotter._save_plot("plot1")
        plt.savefig.assert_called_once()
        plt.show.assert_called_once()

    def test__create_subplot_df(self):
        # TODO as will be refactored
        pass

    def test__concat_subplot_df_to_axs(self):
        pass

    def test__dump_file_mean_into_df_error(self):
        plotter = Plotter({})
        with self.assertRaises(Exception):
            plotter._dump_file_mean_into_df("test", pd.DataFrame())

    def test__add_median_labels(self):
        pass




