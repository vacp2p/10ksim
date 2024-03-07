# Python Imports
import logging
import os
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from typing import List, Dict
from matplotlib import ticker

# Project Imports
from utils.file_utils import get_files_from_folder_path, get_file_name_from_path

logger = logging.getLogger(__name__)
sns.set_theme()


class Plotter:
    def __init__(self, plot_config: Dict):
        self._config = plot_config

    def create_plots(self):
        for plot_name, plot_specs in self._config.items():
            self._create_plot(plot_name, plot_specs)

    def _create_plot(self, plot_name: str, plot_specs: Dict):
        fig, axs = plt.subplots(nrows=1, ncols=len(plot_specs['data']), sharey='row', figsize=(15,15))

        subplot_paths_group = self._create_subplot_paths_group(plot_specs)

        for i, subplot_path_group in enumerate(subplot_paths_group):
            subplot_title = subplot_path_group[1]
            self._create_subplot(subplot_path_group[0], subplot_title, i, axs)

        self._save_plot(plot_name)

    def _save_plot(self, plot_name: str):
        plt.tight_layout()
        plt.savefig(plot_name)
        plt.show()

    def _create_subplot(self, subplot_paths_group: str, subplot_title: str, index: int, axs: np.ndarray):
        subplot_df = pd.DataFrame()

        for subplot_path in subplot_paths_group:
            group_df = pd.DataFrame()
            data_files_path = get_files_from_folder_path(subplot_path)

            for file_path in data_files_path:
                group_df = self._dump_file_mean_into_df(subplot_path+"/"+file_path, group_df)

            group_df["class"] = subplot_path.split("/")[-2]
            subplot_df = pd.concat([subplot_df, group_df])

        subplot_df = pd.melt(subplot_df, id_vars=["class"])

        self._add_subplot_to_axs(subplot_df, index, subplot_title, axs)

    def _add_subplot_to_axs(self, df: pd.DataFrame, index: int, subplot_title: str, axs: np.ndarray):
        box_plot = sns.boxplot(data=df, x="variable", y="value", hue="class", ax=axs[index],
                               showfliers=False)

        # Apply the custom formatter to the x-axis ticks
        formatter = ticker.FuncFormatter(lambda x, pos: '{:.0f}'.format(x / 1000))
        box_plot.yaxis.set_major_formatter(formatter)

        box_plot.set(xlabel='NºNodes-MsgRate', ylabel=f"KBytes/s")
        box_plot.set_title(f'{subplot_title}')
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)

        self.add_median_labels(box_plot)

    def _dump_file_mean_into_df(self, file_path: str, group_df: pd.DataFrame):
        if not os.path.exists(file_path):
            logger.error(f"Missing {file_path}")
            return

        file_name = get_file_name_from_path(file_path)

        df = pd.read_csv(file_path, parse_dates=['Time'], index_col='Time')
        df_mean = df.mean()
        df_mean = pd.DataFrame(df_mean, columns=[file_name])
        group_df = pd.concat([group_df, df_mean], axis=1)

        return group_df

    def _create_subplot_paths_group(self, plot_specs: Dict) -> List:
        subplot_path = [
            ([f"{folder}{data}" for folder in plot_specs["folder"]], data) for data in plot_specs["data"]

        ]

        return subplot_path

    def add_median_labels(self, ax: plt.Axes, fmt: str = ".3f") -> None:
        # https://stackoverflow.com/a/63295846
        """Add text labels to the median lines of a seaborn boxplot.

        Args:
            ax: plt.Axes, e.g. the return value of sns.boxplot()
            fmt: format string for the median value
        """
        lines = ax.get_lines()
        boxes = [c for c in ax.get_children() if "Patch" in str(c)]
        start = 4
        if not boxes:  # seaborn v0.13 => fill=False => no patches => +1 line
            boxes = [c for c in ax.get_lines() if len(c.get_xdata()) == 5]
            start += 1
        lines_per_box = len(lines) // len(boxes)
        for median in lines[start::lines_per_box]:
            x, y = (data.mean() for data in median.get_data())
            # choose value depending on horizontal or vertical plot orientation
            value = x if len(set(median.get_xdata())) == 1 else y
            text = ax.text(x, y, f'{value/1000:{fmt}}', ha='center', va='center',
                           fontweight='bold', color='white')
            # create median-colored border around white text for contrast
            text.set_path_effects([
                path_effects.Stroke(linewidth=3, foreground=median.get_color()),
                path_effects.Normal(),
            ])
