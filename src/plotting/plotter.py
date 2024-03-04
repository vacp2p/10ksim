# Python Imports
import os

import numpy as np

import logger
import pandas as pd
import seaborn as sns
from typing import List, Dict
import matplotlib.pyplot as plt
from matplotlib import ticker
from matplotlib.axis import Axis

# Project Imports
from utils.file_utils import get_files_from_folder_path, get_file_name_from_path

# logger = logging.getLogger(__name__)
sns.set_theme()
# En carpeta: metrica1, metrica2, metrica3...
# o bien, metrica1_1, metrica1_2...
# La carpeta padre, es carpetas de carpetas de metricas ()


# Cuando se descarga, se crea la carpeta del experimento
# Del experimento, se pueden crear plots (metrica),
# Del experimento, se pueden meter varios plots juntos (metricas para comparar, RX-TX)
# Pensar que del mismo experimento, se puedan meter varios plots por fila (compactación)
# De varios experimentos, se pueden meter en el mismo plot (metrica)


# test = {"bandwidth": {"folder": ["waku"], "data": ["RX", "TX"], "include": ["experiment1", "experiment2"]}}
# Del tipo de programa "FOLDER", quiero que me plotees rx contra tx, y que me incluyas los experimentos x y z
# en este caso se plotearán tantos plots como "data" haya. con INCLUDE boxplots, y FOLDER tipos de boxplots.
# test = {"bandwidth": {"folder": ["../../data/plotter_data_test/rust/", "../../data/plotter_data_test/go/"], "data": ["rx", "tx"], "include": ["0.5KB-1.csv", "0.5KB-1.csv"]}}
test = {"bandwidth": {"folder": ["../../test/nwaku/1000-1KB-1msgs/"], "data": ["libp2p-rx", "libp2p-tx"], "include": ["0.5KB-1.csv", "0.5KB-1.csv"]}}


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
                group_df = self._dump_file_mean_into_df(file_path, group_df)

            subplot_df["class"] = subplot_path.split("/")[-2]
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


def add_data_to_df(main_df, df: pd.DataFrame, name):
    df_avg = df.mean()
    df_avg = pd.DataFrame(df_avg, columns=[name])

    concat_df = pd.concat([main_df, df_avg], axis=1)

    return concat_df


def create_plot():
    fig, axs = plt.subplots(nrows=1, ncols=2, sharey='row')

    folders_grouped = [
        [f"{folder}{data}" for folder in test["bandwidth"]["folder"]]
        for data in test["bandwidth"]["data"]
    ]

    for k, group in enumerate(folders_grouped):
        main_df = pd.DataFrame()
        for folder_path in group:
            folder_df = pd.DataFrame()
            files = [f for f in os.listdir(folder_path) if
                     os.path.isfile(os.path.join(folder_path, f))]
            for file in files:
                if not os.path.exists(folder_path+"/"+file): continue  # todo delete this line
                df = pd.read_csv(folder_path+"/"+file, parse_dates=['Time'],
                                 index_col='Time')
                folder_df = add_data_to_df(folder_df, df, file)

            folder_df["class"] = folder_path.split("/")[-2]
            main_df = pd.concat([main_df, folder_df])

        main_df = pd.melt(main_df, id_vars=["class"])

        box_plot = sns.boxplot(data=main_df, x="variable", y="value", hue="class", ax=axs[k])
        box_plot.set(xlabel='Payload size (KB)', ylabel=f"Kbytes")
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)

        # formatter = ticker.FuncFormatter(lambda x, pos: '{:.0f}'.format(x / 1000))
        # Apply the custom formatter to the x-axis ticks
        # box_plot.yaxis.set_major_formatter(formatter)

    plt.tight_layout()
    plt.savefig(f"teestt.png")
    plt.show()


create_plot()


def plot_merged(folders_grouped: List, metrics: List):
    fig, axs = plt.subplots(nrows=3, ncols=2, figsize=(14, 16), sharex=True, sharey='row')

    for j, group in enumerate(folders_grouped):
        final_df = pd.DataFrame()
        for i, folder_path in enumerate(group):
            if not os.path.exists(folder_path): continue
            files = [f for f in os.listdir(folder_path) if
                     os.path.isfile(os.path.join(folder_path, f))]
            files = sorted(files, key=lambda x: float(x.split("-")[1].split("KB")[0]))
            folder_df = pd.DataFrame()

            for file in files:
                df = pd.read_csv(folder_path + file, parse_dates=['Time'], index_col='Time')

                column_name = file.split("-")[1]

                df_avg = df.mean()

                folder_df = pd.concat([folder_df, df_avg.rename(column_name)], axis=1)
            folder_df["node"] = language[i]
            final_df = pd.concat([final_df, folder_df])

        final_df = pd.melt(final_df, id_vars=["node"])

        box_plot = sns.boxplot(data=final_df, x="variable", y="value", hue="node",
                               ax=axs[j // 2, j % 2])
        box_plot.set_title(f'{data_to_plot[j]} (N=300)')

        box_plot.set(xlabel='Payload size (KB)', ylabel=f"{y_label[j]}")
        box_plot.tick_params(labelbottom=True)
        # plt.ylabel(f"{y_label[j]}")
        # plt.xlabel('Payload size (KB)')

        # sns.move_legend(box_plot, "upper left", bbox_to_anchor=(1, 1))
        # plt.tight_layout()

        if scale[j]:
            # Create a custom formatter to divide x-axis ticks by 1000
            formatter = ticker.FuncFormatter(lambda x, pos: '{:.0f}'.format(x / 1000))
            # Apply the custom formatter to the x-axis ticks
            box_plot.yaxis.set_major_formatter(formatter)

    plt.tight_layout()
    plt.savefig(f"all.png")
    plt.show()
    # box_plot.figure.savefig(f"{data_to_plot[j]}-melted.png")
