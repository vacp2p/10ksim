# Python Imports
import logging
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from typing import List, Dict
from matplotlib import ticker

# Project Imports
from src.data.data_handler import DataHandler
from src.data.data_file_handler import DataFileHandler

logger = logging.getLogger(__name__)
sns.set_theme()


class Plotter:
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
                               showfliers=True)

        # Apply the custom formatter to the x-axis ticks
        formatter = ticker.FuncFormatter(lambda x, pos: '{:.0f}'.format(x / plot_specs['scale-x']))
        box_plot.yaxis.set_major_formatter(formatter)

        box_plot.set(xlabel=plot_specs['xlabel_name'], ylabel=plot_specs['ylabel_name'])
        box_plot.set_title(f'{subplot_title}')
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)
        box_plot.legend(loc='upper right', bbox_to_anchor=(1, 1))

        self._add_stat_labels(box_plot)
        show_min_max = plot_specs.get("show_min_max", False)
        if show_min_max:
            self._add_stat_labels(box_plot, value_type="min")
            self._add_stat_labels(box_plot, value_type="max")

    def _create_subplot_paths_group(self, plot_specs: Dict) -> List:
        subplot_path = [[f"{folder}{data}" for folder in plot_specs["folder"]] for data in
                        plot_specs["data"]]

        return subplot_path

    def _add_stat_labels(self, ax: plt.Axes, fmt: str = ".3f", value_type: str = "median") -> None:
        # Refactor from https://stackoverflow.com/a/63295846
        """
        Add text labels to the median, minimum, or maximum lines of a seaborn boxplot.

        Args:
            ax: plt.Axes, e.g., the return value of sns.boxplot()
            fmt: Format string for the value (e.g., min/max/median).
            value_type: The type of value to label. Can be 'median', 'min', or 'max'.
        """
        lines = ax.get_lines()
        boxes = [c for c in ax.get_children() if "Patch" in str(c)]  # Get box patches
        start = 4
        if not boxes:  # seaborn v0.13 or above (no patches => need to shift index)
            boxes = [c for c in ax.get_lines() if len(c.get_xdata()) == 5]
            start += 1
        lines_per_box = len(lines) // len(boxes)

        if value_type == "median":
            line_idx = start
        elif value_type == "min":
            line_idx = start - 2  # min line comes 2 positions before the median
        elif value_type == "max":
            line_idx = start - 1  # max line comes 1 position before the median
        else:
            raise ValueError("Invalid value_type. Must be 'min', 'max', or 'median'.")

        for value_line in lines[line_idx::lines_per_box]:
            x, y = (data.mean() for data in value_line.get_data())
            # choose value depending on horizontal or vertical plot orientation
            value = x if len(set(value_line.get_xdata())) == 1 else y
            text = ax.text(x, y, f'{value / 1000:{fmt}}', ha='center', va='center',
                           fontweight='bold', color='white', size=10)
            # create colored border around white text for contrast
            text.set_path_effects([
                path_effects.Stroke(linewidth=3, foreground=value_line.get_color()),
                path_effects.Normal(),
            ])
