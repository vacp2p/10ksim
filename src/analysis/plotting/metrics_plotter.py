import logging
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import ticker
from pydantic import BaseModel

from src.analysis.data.data_file_handler import DataFileHandler
from src.analysis.plotting.config import DataPath, PlotConfig
from src.analysis.utils.plot_utils import add_boxplot_stat_labels

logger = logging.getLogger(__name__)
sns.set_theme()


class MetricsPlotter(BaseModel):
    configs: List[PlotConfig]

    def create_plots(self):
        for plot_config in self.configs:
            logger.info(f'Plotting "{plot_config.name}"')
            self._create_plot(plot_config)
            logger.info(f'Plot "{plot_config.name}" finished')

    def _create_plot(self, plot_specs: PlotConfig):
        fig, axs = plt.subplots(
            nrows=1,
            ncols=len(plot_specs.metrics),
            sharey="row",
            figsize=plot_specs.fig_size,
        )

        if len(plot_specs.metrics) == 1:
            axs = np.array([axs])

        self._insert_data_in_axs(plot_specs, axs)
        self._save_plot(f"{plot_specs.name}.jpg")

    def _insert_data_in_axs(self, plot_specs: PlotConfig, axs: np.ndarray):
        for i, metric in enumerate(plot_specs.metrics):
            metric_df = pd.DataFrame()

            for group in plot_specs.groups:
                file_data_handler = DataFileHandler(plot_specs.ignore_columns)
                named_files = [
                    DataPath(name=data_path.name, path=data_path.path / metric)
                    for data_path in group.data_paths
                ]
                logger.debug(f"named_files: {named_files}")

                file_data_handler.concat_dataframes_from_files(
                    named_files, group.name, plot_specs.data_points
                )

                group_df = file_data_handler.dataframe
                if not len(group_df):
                    raise ValueError(
                        f"Failed to read dataframe. Check the input file.\n"
                        f"Subplot paths: `{group.data_paths}`\n"
                        f"Subplot name: `{group.name}`"
                    )

                metric_df = pd.concat([metric_df, group_df], ignore_index=True)

            # Melt numeric columns only, keep class and variable as identifiers
            metric_df = pd.melt(
                metric_df, id_vars=["class", "variable"], var_name="metric", value_name="value"
            )
            plot_specs_dict = plot_specs.model_dump()
            self._add_subplot_df_to_axs(metric_df, i, axs, plot_specs_dict, metric)

    def _save_plot(self, plot_name: str):
        plt.tight_layout()
        plt.savefig(plot_name)

    def _add_subplot_df_to_axs(
        self, df: pd.DataFrame, index: int, axs: np.ndarray, plot_specs: Dict, metric: str
    ):
        ax = axs[index] if isinstance(axs, np.ndarray) else axs

        hue_col = plot_specs.get("hue", "class")

        # order of clusters of data along the x-axis
        x_order = plot_specs.get("x_order")
        if x_order and "variable" in df.columns:
            df["variable"] = pd.Categorical(df["variable"], categories=x_order, ordered=True)
            df = df.sort_values("variable", kind="stable")

        # order of values in the legend
        legend_order = plot_specs.get("legend_order")
        if legend_order and "class" in df.columns:
            df["class"] = pd.Categorical(df["class"], categories=legend_order, ordered=True)
            df = df.sort_values("class", kind="stable")

        box_plot = sns.boxplot(
            data=df,
            x="variable",
            y="value",
            hue=hue_col,
            order=x_order,
            hue_order=legend_order,
            ax=ax,
            showfliers=plot_specs.get("outliers", True),
        )

        formatter = ticker.FuncFormatter(lambda x, pos: "{:.0f}".format(x / plot_specs["scale_x"]))
        box_plot.yaxis.set_major_formatter(formatter)

        box_plot.set(xlabel=plot_specs["xlabel_name"], ylabel=plot_specs["ylabel_name"])
        box_plot.set_title(metric)
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)
        box_plot.legend(loc="upper right", bbox_to_anchor=(1, 1))

        result = add_boxplot_stat_labels(box_plot, scale_by=plot_specs.get("scale_x", 1))
        if result.is_err():
            logger.error(result.err_value)

        if plot_specs.get("show_min_max", False):
            result = add_boxplot_stat_labels(
                box_plot, value_type="min", scale_by=plot_specs.get("scale_x", 1)
            )
            if result.is_err():
                logger.error(result.err_value)

            result = add_boxplot_stat_labels(
                box_plot, value_type="max", scale_by=plot_specs.get("scale_x", 1)
            )
            if result.is_err():
                logger.error(result.err_value)
