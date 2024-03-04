# Python Imports
import logging
import os
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from typing import List, Dict

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
        fig, axs = plt.subplots(nrows=1, ncols=len(plot_specs['data']), sharex=True, sharey='row')

        subplot_paths_group = self._create_subplot_paths_group(plot_specs)

        for i, subplot_path_group in enumerate(subplot_paths_group):
            self._create_subplot(subplot_path_group, i, axs)

        self._save_plot(plot_name)

    def _save_plot(self, plot_name: str):
        plt.tight_layout()
        plt.savefig(plot_name)
        plt.show()

    def _create_subplot(self, subplot_paths_group: str, index: int, axs: np.ndarray):
        subplot_df = pd.DataFrame()

        for subplot_path in subplot_paths_group:
            group_df = pd.DataFrame()
            data_files_path = get_files_from_folder_path(subplot_path)

            for file_path in data_files_path:
                group_df = self._dump_file_mean_into_df(subplot_path+"/"+file_path, group_df)

            group_df["class"] = subplot_path.split("/")[-2]
            subplot_df = pd.concat([subplot_df, group_df])

        subplot_df = pd.melt(subplot_df, id_vars=["class"])

        self._add_subplot_to_axs(subplot_df, index, axs)

    def _add_subplot_to_axs(self, df: pd.DataFrame, index: int, axs: np.ndarray):
        box_plot = sns.boxplot(data=df, x="variable", y="value", hue="class", ax=axs[index])
        box_plot.set(xlabel='Payload size (KB)', ylabel=f"Kbytes")
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)

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
            [f"{folder}{data}" for folder in plot_specs["folder"]] for data in plot_specs["data"]
        ]

        return subplot_path
