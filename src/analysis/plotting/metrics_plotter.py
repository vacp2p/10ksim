import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import ticker
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from src.analysis.data.data_file_handler import DataFileHandler
from src.analysis.data.data_handler import DataHandler
from src.analysis.utils.plot_utils import add_boxplot_stat_labels
from src.plotting.config import PlotConfig

logger = logging.getLogger(__name__)
sns.set_theme()


class TimeInterval(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    start: datetime
    end: datetime


class TimeRange(BaseModel):
    """Time range.
    - Parses time str to remove the "T"
    - Requires that start <= end
    """

    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @field_validator("start", "end", mode="before")
    @classmethod
    def _parse_start_end(cls, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            normalized_string = value.replace("T", " ")
            format_string = "%Y-%m-%d %H:%M:%S"
            try:
                return datetime.strptime(normalized_string, format_string)
            except ValueError:
                raise ValueError(f"Invalid datetime string: {value}")
        raise TypeError("start/end must be datetime, str, or None")

    @model_validator(mode="after")
    def _ensure_end_after_start(self) -> "TimeRange":
        if self.start is not None and self.end is not None and self.end < self.start:
            raise ValueError("end must be after start")
        return self

    def __str__(self) -> str:
        start_s = self.start.strftime("%Y-%m-%d %H:%M:%S") if self.start else None
        end_s = self.end.strftime("%Y-%m-%d %H:%M:%S") if self.end else None
        return f"TimeRange(start={start_s!r}, end={end_s!r})"


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
            ncols=len(plot_specs.data),
            sharey="row",
            figsize=plot_specs.fig_size,
        )

        # TODO [plotter config]: Edit logic. Change config.
        subplot_paths_group = self._create_subplot_paths_group(plot_specs)
        self._insert_data_in_axs(subplot_paths_group, axs, plot_specs)
        self._save_plot(f"{plot_specs.name}.jpg")

    def _insert_data_in_axs(self, subplot_paths_group: List, axs: np.ndarray, plot_specs: Dict):
        for i, subplot_path_group in enumerate(subplot_paths_group):
            file_data_handler = DataFileHandler(plot_specs.ignore_columns, plot_specs.include_files)
            file_data_handler.concat_dataframes_from_folders_as_mean(
                subplot_path_group, plot_specs.data_points
            )
            subplot_df = file_data_handler.dataframe

            subplot_df = DataHandler.prepare_dataframe_for_boxplot(subplot_df)
            plot_specs_dict = plot_specs.model_dump()
            self._add_subplot_df_to_axs(subplot_df, i, axs, plot_specs_dict)

    def _save_plot(self, plot_name: str):
        plt.tight_layout()
        plt.savefig(plot_name)
        plt.show()

    def _add_subplot_df_to_axs(
        self, df: pd.DataFrame, index: int, axs: np.ndarray, plot_specs: Dict
    ):
        subplot_title = plot_specs["data"][index]
        axs = axs if type(axs) is not np.ndarray else axs[index]

        hue_col = plot_specs.get("hue", "class")
        custom_order = plot_specs.get("plot_order")

        if custom_order:
            df["variable"] = pd.Categorical(df["variable"], categories=custom_order, ordered=True)

        if hue_col == "variable":
            # Hue is the same as x-axis → use custom_order
            hue_order = custom_order
        elif hue_col == "class":
            # Hue is class → order by unique classes unless user specifies otherwise later
            hue_order = sorted(df["class"].unique())

        box_plot = sns.boxplot(
            data=df,
            x="variable",
            y="value",
            hue=hue_col,
            order=custom_order,
            hue_order=hue_order,
            ax=axs,
            showfliers=plot_specs.get("outliers", True),
        )

        # Apply the custom formatter to the x-axis ticks

        formatter = ticker.FuncFormatter(lambda x, pos: "{:.0f}".format(x / plot_specs["scale_x"]))
        box_plot.yaxis.set_major_formatter(formatter)

        box_plot.set(xlabel=plot_specs["xlabel_name"], ylabel=plot_specs["ylabel_name"])
        box_plot.set_title(f"{subplot_title}")
        box_plot.tick_params(labelbottom=True)
        box_plot.xaxis.set_tick_params(rotation=45)
        box_plot.legend(loc="upper right", bbox_to_anchor=(1, 1))

        result = add_boxplot_stat_labels(box_plot, scale_by=plot_specs.get("scale_x", 1))
        if result.is_err():
            logger.error(result.err_value)

        show_min_max = plot_specs.get("show_min_max", False)
        if show_min_max:
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

    def _create_subplot_paths_group(self, plot_specs: PlotConfig) -> List:
        subplot_path = [
            [f"{folder}{data}" for folder in plot_specs.folder] for data in plot_specs.data
        ]

        return subplot_path
