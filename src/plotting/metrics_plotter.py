# Python Imports
import logging
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from typing import List, Dict
from matplotlib import ticker

# Project Imports
from src.data.data_handler import DataHandler
from src.data.data_file_handler import DataFileHandler
from src.utils.plot_utils import add_boxplot_stat_labels

logger = logging.getLogger(__name__)
sns.set_theme()


class MetricsPlotter:
    def __init__(self, plot_config: Dict):
        self._config = plot_config

    def create_plots(self):
        for plot_name, plot_specs in self._config.items():
            logger.info(f'Plotting "{plot_name}"')
            self._create_plot(plot_name, plot_specs)
            logger.info(f"Plot \"{plot_name}\" finished")

    def _create_plot(self, plot_name: str, plot_specs: Dict):
        fig, axs = plt.subplots(nrows=1, ncols=len(plot_specs['data']), sharey='row',
                                figsize=plot_specs['fig_size'])

        subplot_paths_group = self._create_subplot_paths_group(plot_specs)
        self._insert_data_in_axs(subplot_paths_group, axs, plot_specs)
        self._save_plot(plot_name)

    def _insert_data_in_axs(self, subplot_paths_group: List, axs: np.ndarray, plot_specs: Dict):
        for i, subplot_path_group in enumerate(subplot_paths_group):
            include_files = plot_specs.get("include_files")
            file_data_handler = DataFileHandler(plot_specs['ignore_columns'], include_files)
            file_data_handler.concat_dataframes_from_folders_as_mean(subplot_path_group,
                                                                     plot_specs['data_points'])
            subplot_df = file_data_handler.dataframe

            subplot_df = DataHandler.prepare_dataframe_for_boxplot(subplot_df)
            self._add_subplot_df_to_axs(subplot_df, i, axs, plot_specs)

    def _save_plot(self, plot_name: str):
        plt.tight_layout()
        plt.savefig(plot_name)
        plt.show()

    def _add_subplot_df_to_axs(self, df: pd.DataFrame, index: int, axs: np.ndarray,
                               plot_specs: Dict):
        subplot_title = plot_specs['data'][index]
        axs = axs if type(axs) is not np.ndarray else axs[index]
        box_plot = sns.boxplot(data=df, x="variable", y="value", hue="class", ax=axs,
                               showfliers=plot_specs.get('outliers', True))

        # Apply the custom formatter to the x-axis ticks
        formatter = ticker.FuncFormatter(lambda x, pos: '{:.0f}'.format(x / plot_specs['scale-x']))
        box_plot.yaxis.set_major_formatter(formatter)

        box_plot.set(xlabel=plot_specs['xlabel_name'], ylabel=plot_specs['ylabel_name'])
        box_plot.set_title(f'{subplot_title}')
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)
        box_plot.legend(loc='upper right', bbox_to_anchor=(1, 1))

        result = add_boxplot_stat_labels(box_plot, scale_by=1/plot_specs['scale-x'])
        if result.is_err():
            logger.error(result.err_value)

        show_min_max = plot_specs.get("show_min_max", False)
        if show_min_max:
            result = add_boxplot_stat_labels(box_plot, value_type="min", scale_by=0.001)
            if result.is_err():
                logger.error(result.err_value)

            result = add_boxplot_stat_labels(box_plot, value_type="max", scale_by=0.001)
            if result.is_err():
                logger.error(result.err_value)

    def _create_subplot_paths_group(self, plot_specs: Dict) -> List:
        subplot_path = [[f"{folder}{data}" for folder in plot_specs["folder"]] for data in
                        plot_specs["data"]]

        return subplot_path


