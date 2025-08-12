# Python Imports
import unittest
import pandas as pd
from unittest.mock import MagicMock, patch

# Project Imports
from src.plotting.metrics_plotter import MetricsPlotter


class TestPlotter(unittest.TestCase):

    def test_create_plots(self):
        config = {"plot1": {}, "plot2": {}}
        plotter = MetricsPlotter(config)

        plotter._create_plot = MagicMock()
        plotter.create_plots()
        self.assertEqual(plotter._create_plot.call_count, 2)

    def test__create_plot(self):
        plotter = MetricsPlotter({})
        plotter._create_subplot_paths_group = MagicMock()
        plotter._insert_data_in_axs = MagicMock()
        plotter._save_plot = MagicMock()

        plotter._create_plot("", {'data': [0]})
        self.assertEqual(plotter._create_subplot_paths_group.call_count, 1)
        self.assertEqual(plotter._insert_data_in_axs.call_count, 1)
        self.assertEqual(plotter._save_plot.call_count, 1)

    @patch('src.plotting.plotter.DataFileHandler.add_dataframes_from_folders_as_mean')
    @patch('src.plotting.plotter.DataHandler.prepare_dataframe_for_boxplot')
    def test__insert_data_in_axs(self, mock_data_file_handler, mock_data_handler):
        plotter = MetricsPlotter({})
        plotter._add_subplot_df_to_axs = MagicMock()
        plotter._insert_data_in_axs([["path1"], ["path2"]], [0], {"data": ["data1"]})

        self.assertEqual(mock_data_file_handler.call_count, 2)
        self.assertEqual(mock_data_handler.call_count, 2)
        self.assertEqual(plotter._add_subplot_df_to_axs.call_count, 2)

    def test__save_plot(self):
        plotter = MetricsPlotter({})
        with patch('matplotlib.pyplot.tight_layout') as mock_tight_layout:
            with patch('matplotlib.pyplot.savefig') as mock_savefig:
                with patch('matplotlib.pyplot.show') as mock_show:
                    plotter._save_plot("plot_name")
                    self.assertEqual(mock_tight_layout.call_count, 1)
                    self.assertEqual(mock_savefig.call_count, 1)
                    self.assertEqual(mock_show.call_count, 1)

    def test__add_subplot_df_to_axs(self):
        plotter = MetricsPlotter({})

        with patch('seaborn.boxplot') as mock_boxplot:
            with patch('src.plotting.plotter.Plotter._add_median_labels') as mock_add_median_labels:
                mock_boxplot.return_value = MagicMock()
                plotter._add_subplot_df_to_axs(pd.DataFrame(), 0, [0],
                                               {"data": ["data1"],
                                                "xlabel_name": "test", "ylabel_name": "test", "scale-x": 1})
                self.assertEqual(mock_boxplot.return_value.set.call_count, 1)
                self.assertEqual(mock_boxplot.return_value.yaxis.set_major_formatter.call_count, 1)
                self.assertEqual(mock_boxplot.return_value.set_title.call_count, 1)
                self.assertEqual(mock_boxplot.return_value.tick_params.call_count, 1)
                self.assertEqual(mock_boxplot.return_value.xaxis.set_tick_params.call_count, 1)
                self.assertEqual(mock_add_median_labels.call_count, 1)

    def test_create_subplot_paths_group(self):
        plotter = MetricsPlotter({})
        plot_specs = {
            "folder": ["test/nwaku/", "test/nwaku0.26/"],
            "data": ["libp2p-in", "libp2p-out"]
        }

        result = plotter._create_subplot_paths_group(plot_specs)
        expected = [["test/nwaku/libp2p-in", "test/nwaku0.26/libp2p-in"],
                    ["test/nwaku/libp2p-out", "test/nwaku0.26/libp2p-out"]]

        self.assertEqual(result, expected)




