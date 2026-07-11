"""Panel processor - processes panel configurations and transformations."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any
from collections import defaultdict
from copy import deepcopy

from dst_dashboard.config.data_structures import (
    PanelConfig,
    ExperimentConfig,
    DashboardFullConfig
)
from dst_dashboard.storage.db import DSTDatabase
from dst_dashboard.processors.dataset_processor import DatasetProcessor

logger = logging.getLogger(__name__)


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries. Override values take precedence."""
    result = deepcopy(base)
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    
    return result


class PanelProcessor(DatasetProcessor):
    """
    Panel processor - inherits from DatasetProcessor.
    
    Processes panel configurations, transforms data, and generates ECharts-ready specs.
    Hierarchy: ExperimentProcessor -> PanelProcessor -> DatasetProcessor
    """

    def __init__(self, config: DashboardFullConfig, db: DSTDatabase):
        super().__init__(config, db)

    def process_panel(
        self,
        experiment_id: str,
        panel_config: PanelConfig
    ) -> bool:
        """Process and store panel ECharts options. Returns True on success."""
        logger.info(f"Processing panel: {panel_config.name}")
        
        # Verify that the dataset for this panel exists
        if not self.db.dataset_exists(experiment_id, panel_config.dataset):
            logger.warning(
                f"Panel '{panel_config.name}' references non-existent dataset '{panel_config.dataset}', skipping"
            )
            return False
        
        try:
            # Generate and store ECharts options
            echarts_option = self.transform_panel_data(experiment_id, panel_config)
            self.db.store_panel_data(experiment_id, panel_config.name, echarts_option)
            logger.info(f"Panel '{panel_config.name}' processed and stored successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to process panel '{panel_config.name}': {e}", exc_info=True)
            return False

    def process_experiment_panels(
        self,
        experiment: ExperimentConfig,
        max_workers: int = 4
    ) -> int:
        """Process all panels for an experiment concurrently. Returns the number processed successfully."""
        if not experiment.panels:
            return 0

        if len(experiment.panels) == 1 or max_workers <= 1:
            return sum(
                self.process_panel(experiment.id, panel_config)
                for panel_config in experiment.panels
            )

        success_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.process_panel, experiment.id, panel_config): panel_config
                for panel_config in experiment.panels
            }
            for future in as_completed(futures):
                panel_config = futures[future]
                try:
                    if future.result():
                        success_count += 1
                except Exception:
                    logger.error(
                        f"Panel '{panel_config.name}' processing raised unexpectedly", exc_info=True
                    )

        return success_count
    
    def _apply_derive_transformations(self, data: List[Dict[str, Any]], panel_config: PanelConfig) -> List[Dict[str, Any]]:
        """Apply derive transformations to create new fields."""
        if not panel_config.transform or not panel_config.transform.derive:
            return data
        
        result = []
        for row in data:
            new_row = row.copy()
            
            for derive in panel_config.transform.derive:
                if derive.function == "regex_match":
                    # Apply regex pattern to field
                    field_value = str(row.get(derive.field, ""))
                    if derive.pattern and re.search(derive.pattern, field_value):
                        new_row[derive.name] = derive.match or "match"
                    else:
                        new_row[derive.name] = derive.no_match or "no_match"
                else:
                    logger.warning(f"Unknown derive function: {derive.function}")
            
            result.append(new_row)
        
        return result
    
    def _transform_to_boxplot(self, data: List[Dict[str, Any]], panel_config: PanelConfig) -> Dict[str, Any]:
        """Transform data for ECharts boxplot visualization."""
        transform = panel_config.transform
        group_by = transform.groupBy
        value_field = transform.value
        
        if not group_by or not value_field:
            raise ValueError("Boxplot requires 'groupBy' and 'value' in transform")
        
        # Group data by the groupBy field
        grouped_data = defaultdict(list)
        for row in data:
            group_key = row.get(group_by, "unknown")
            value = row.get(value_field)
            if value is not None:
                grouped_data[group_key].append(float(value))
        
        # Apply top filter if specified - sort by average value
        if transform.top:
            # Calculate average for each group
            group_stats = []
            for group_name, values in grouped_data.items():
                avg_val = sum(values) / len(values) if values else 0
                group_stats.append((group_name, avg_val, values))
            
            # Sort by average value (descending) and take top N
            group_stats.sort(key=lambda x: x[1], reverse=True)
            top_groups = group_stats[:transform.top]
            
            # Rebuild grouped_data with only top groups
            grouped_data = {name: values for name, _, values in top_groups}
        
        # Sort categories and calculate boxplot stats
        categories = sorted(grouped_data.keys())
        boxplot_data = []
        
        for category in categories:
            values = sorted(grouped_data[category])
            if not values:
                continue
            
            n = len(values)
            min_val = values[0]
            max_val = values[-1]
            median = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2
            q1 = values[n // 4]
            q3 = values[3 * n // 4]
            
            # ECharts boxplot format: [min, Q1, median, Q3, max]
            boxplot_data.append([min_val, q1, median, q3, max_val])
        
        # Build ECharts option
        option = {
            "backgroundColor": "transparent",
            "title": {
                "text": panel_config.title,
                "left": "center",
                "textStyle": {
                    "color": "#152521"
                }
            },
            "tooltip": {
                "trigger": "item",
                "axisPointer": {"type": "shadow"}
            },
            "toolbox": {
                "feature": {
                    "dataZoom": {
                        "yAxisIndex": "none",
                        "title": {"zoom": "Area Zoom", "back": "Reset"}
                    },
                    "restore": {"title": "Restore"},
                    "saveAsImage": {"title": "Save"}
                },
                "iconStyle": {
                    "borderColor": "#848e88"
                },
                "emphasis": {
                    "iconStyle": {
                        "borderColor": "#00d4ff"
                    }
                }
            },
            "dataZoom": [
                {
                    "type": "inside",
                    "xAxisIndex": 0,
                    "filterMode": "none",
                    "disabled": False
                }
            ],
            "grid": {
                "left": "10%",
                "right": "10%",
                "bottom": "15%"
            },
            "xAxis": {
                "type": "category",
                "data": categories,
                "boundaryGap": True,
                "splitArea": {"show": False},
                "axisLabel": {"color": "#475651"},
                "axisLine": {"lineStyle": {"color": "#b8bdb8"}}
            },
            "yAxis": {
                "type": "value",
                "splitArea": {"show": False},
                "axisLabel": {"color": "#475651"},
                "axisLine": {"lineStyle": {"color": "#b8bdb8"}},
                "splitLine": {"lineStyle": {"color": "#eceee4"}}
            },
            "series": [
                {
                    "name": panel_config.title,
                    "type": "boxplot",
                    "data": boxplot_data,
                    "itemStyle": {
                        "borderColor": "#00d4ff",
                        "borderWidth": 1.5
                    }
                }
            ]
        }
        
        # Add optional style configurations
        if panel_config.style:
            if panel_config.style.xLabel:
                option["xAxis"]["name"] = panel_config.style.xLabel
            if panel_config.style.yLabel:
                option["yAxis"]["name"] = panel_config.style.yLabel
            if panel_config.style.yMin is not None:
                option["yAxis"]["min"] = panel_config.style.yMin
            if panel_config.style.yMax is not None:
                option["yAxis"]["max"] = panel_config.style.yMax
        
        # Merge user-provided ECharts options (if any)
        if panel_config.echarts_options:
            option = deep_merge(option, panel_config.echarts_options)
        
        return option
    
    def _transform_to_timeseries(self, data: List[Dict[str, Any]], panel_config: PanelConfig) -> Dict[str, Any]:
        """Transform data for ECharts timeseries (line chart) visualization."""
        transform = panel_config.transform
        x_field = transform.x
        y_field = transform.y
        
        if not x_field or not y_field:
            raise ValueError("Timeseries requires 'x' and 'y' in transform")
        
        # Group by a categorical field if groupBy is specified (for multi-series)
        if transform.groupBy:
            grouped_series = defaultdict(list)
            
            for row in data:
                group_key = row.get(transform.groupBy, "default")
                x_val = row.get(x_field)
                y_val = row.get(y_field)
                
                if x_val is not None and y_val is not None:
                    # Convert datetime to ISO string for JSON serialization
                    x_val_serialized = x_val.isoformat() if hasattr(x_val, 'isoformat') else str(x_val)
                    grouped_series[group_key].append({
                        "timestamp": x_val_serialized,
                        "value": float(y_val)
                    })
            
            # Apply top filter if specified (limit number of series)
            if transform.top:
                # Sort by average value to get most significant series
                series_stats = []
                for group_name, points in grouped_series.items():
                    avg_val = sum(p["value"] for p in points) / len(points) if points else 0
                    series_stats.append((group_name, avg_val, points))
                
                # Sort by average value (descending) and take top N
                series_stats.sort(key=lambda x: x[1], reverse=True)
                top_series = dict((name, points) for name, _, points in series_stats[:transform.top])
                grouped_series = top_series
            elif transform.firstN:
                # Take first N series by name (no sorting by value)
                sorted_names = sorted(grouped_series.keys())[:transform.firstN]
                grouped_series = {name: grouped_series[name] for name in sorted_names}
            
            # Professional color palette - distinct and readable
            colors = [
                "#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de",
                "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc", "#d4a5a5"
            ]
            
            # Build series for each group
            series = []
            for idx, (group_name, points) in enumerate(sorted(grouped_series.items())):
                # Sort points by timestamp to ensure proper line drawing
                sorted_points = sorted(points, key=lambda p: p["timestamp"])
                
                # Create [timestamp, value] pairs for ECharts - properly ordered
                data_pairs = [[p["timestamp"], p["value"]] for p in sorted_points]
                
                color = colors[idx % len(colors)]
                series.append({
                    "name": str(group_name),
                    "type": "line",
                    "data": data_pairs,
                    "smooth": False,
                    "sampling": "lttb",
                    "symbol": "none",
                    "connectNulls": False,  # Don't connect gaps
                    "lineStyle": {
                        "width": 1.5,
                        "color": color
                    },
                    "emphasis": {
                        "focus": "series",
                        "lineStyle": {
                            "width": 2.5
                        }
                    }
                })

        else:
            # Single series
            x_values = []
            y_values = []
            
            for row in data:
                x_val = row.get(x_field)
                y_val = row.get(y_field)
                
                if x_val is not None and y_val is not None:
                    # Convert datetime to ISO string for JSON serialization
                    x_val_serialized = x_val.isoformat() if hasattr(x_val, 'isoformat') else str(x_val)
                    x_values.append(x_val_serialized)
                    y_values.append(float(y_val))
            
            series = [{
                "name": panel_config.title,
                "type": "line",
                "data": y_values,
                "smooth": True,
                "sampling": "lttb",
                "symbol": "none",
                "lineStyle": {
                    "width": 2,
                    "color": "#00d4ff"
                },
                "areaStyle": {
                    "color": "#00d4ff",
                    "opacity": 0.15
                }
            }]
        
        # Build ECharts option
        option = {
            "backgroundColor": "transparent",
            "title": {
                "text": panel_config.title,
                "left": "center",
                "top": 10,
                "textStyle": {
                    "color": "#152521",
                    "fontSize": 16,
                    "fontWeight": "normal"
                }
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {
                    "type": "line",
                    "lineStyle": {
                        "color": "#b8bdb8",
                        "type": "dashed"
                    }
                },
                "backgroundColor": "rgba(245, 245, 239, 0.95)",
                "borderColor": "#dbddd7",
                "borderWidth": 1,
                "textStyle": {
                    "color": "#152521",
                    "fontSize": 12
                },
                "confine": True
            },
            "legend": {
                "type": "scroll",
                "data": [s["name"] for s in series],
                "bottom": 5,
                "left": "center",
                "textStyle": {
                    "color": "#475651",
                    "fontSize": 11
                },
                "pageIconColor": "#5470c6",
                "pageIconInactiveColor": "#dbddd7",
                "pageTextStyle": {
                    "color": "#475651"
                },
                "icon": "roundRect"
            },
            "toolbox": {
                "show": True,
                "feature": {
                    "dataZoom": {
                        "yAxisIndex": "none",
                        "title": {"zoom": "Area Zoom", "back": "Reset"}
                    },
                    "restore": {"title": "Restore"},
                    "saveAsImage": {"title": "Save"}
                },
                "iconStyle": {
                    "borderColor": "#848e88"
                },
                "emphasis": {
                    "iconStyle": {
                        "borderColor": "#5470c6"
                    }
                },
                "top": 10,
                "right": 20
            },
            "dataZoom": [
                {
                    "type": "inside",
                    "xAxisIndex": 0,
                    "filterMode": "none"
                }
            ],
            "grid": {
                "left": "3%",
                "right": "4%",
                "bottom": "50px",
                "top": "60px",
                "containLabel": True
            },
            "xAxis": {
                "type": "time",
                "boundaryGap": False,
                "axisLabel": {
                    "color": "#475651",
                    "fontSize": 11,
                    "formatter": "{HH}:{mm}"
                },
                "axisLine": {
                    "lineStyle": {
                        "color": "#b8bdb8"
                    }
                },
                "axisTick": {
                    "show": False
                },
                "splitLine": {
                    "show": False
                }
            },
            "yAxis": {
                "type": "value",
                "axisLabel": {
                    "color": "#475651",
                    "fontSize": 11
                },
                "axisLine": {
                    "show": False
                },
                "axisTick": {
                    "show": False
                },
                "splitLine": {
                    "lineStyle": {
                        "color": "#eceee4",
                        "type": "solid"
                    }
                }
            },
            "series": series
        }
        
        # Add optional style configurations
        if panel_config.style:
            if panel_config.style.xLabel:
                option["xAxis"]["name"] = panel_config.style.xLabel
                option["xAxis"]["nameTextStyle"] = {"color": "#475651", "fontSize": 11}
            if panel_config.style.yLabel:
                option["yAxis"]["name"] = panel_config.style.yLabel
                option["yAxis"]["nameTextStyle"] = {"color": "#475651", "fontSize": 11}
            if panel_config.style.yMin is not None:
                option["yAxis"]["min"] = panel_config.style.yMin
            if panel_config.style.yMax is not None:
                option["yAxis"]["max"] = panel_config.style.yMax
            
            # Add auto-formatting based on unit type
            if panel_config.style.yUnit in ["bytes", "bytes/s", "bps"]:
                option["yAxis"]["axisLabel"]["formatter"] = "__BYTES_FORMATTER__"
                option["tooltip"]["valueFormatter"] = "__BYTES_FORMATTER__"
            elif panel_config.style.yUnit == "ms":
                option["yAxis"]["axisLabel"]["formatter"] = "__MS_FORMATTER__"
                option["tooltip"]["valueFormatter"] = "__MS_FORMATTER__"
            elif panel_config.style.yUnit == "seconds":
                option["yAxis"]["axisLabel"]["formatter"] = "__SECONDS_FORMATTER__"
                option["tooltip"]["valueFormatter"] = "__SECONDS_FORMATTER__"
            elif panel_config.style.yUnit == "percent":
                option["yAxis"]["axisLabel"]["formatter"] = "__PERCENT_FORMATTER__"
                option["tooltip"]["valueFormatter"] = "__PERCENT_FORMATTER__"
            elif panel_config.style.yUnit == "number":
                option["yAxis"]["axisLabel"]["formatter"] = "__NUMBER_FORMATTER__"
                option["tooltip"]["valueFormatter"] = "__NUMBER_FORMATTER__"
        
        # Merge user-provided ECharts options (if any)
        if panel_config.echarts_options:
            option = deep_merge(option, panel_config.echarts_options)
        
        return option
    
    def transform_panel_data(
        self, 
        experiment_id: str, 
        panel_config: PanelConfig,
        viz_format: str = "echarts"
    ) -> Dict[str, Any]:
        """Transform dataset for panel visualization into the requested viz_format."""
        dataset = self.db.get_dataset(experiment_id, panel_config.dataset)
        if not dataset:
            raise ValueError(f"Dataset '{panel_config.dataset}' not found")
        
        # Apply derive transformations
        data = self._apply_derive_transformations(dataset, panel_config)
        
        # Route to appropriate transformer based on viz_format
        if viz_format == "echarts":
            return self._transform_to_echarts(data, panel_config)
        elif viz_format == "plotly":
            # Future: implement Plotly transformer
            raise NotImplementedError("Plotly transformation not yet implemented")
        else:
            raise ValueError(f"Unsupported visualization format: {viz_format}")
    
    def _transform_to_echarts(
        self,
        data: List[Dict[str, Any]],
        panel_config: PanelConfig
    ) -> Dict[str, Any]:
        """Transform data to ECharts format based on panel type."""
        if panel_config.type == "boxplot":
            return self._transform_to_boxplot(data, panel_config)
        elif panel_config.type == "timeseries":
            return self._transform_to_timeseries(data, panel_config)
        elif panel_config.type == "histogram":
            # TODO: Implement histogram transformation
            raise NotImplementedError("Histogram transformation not yet implemented")
        elif panel_config.type == "bar":
            # TODO: Implement bar chart transformation
            raise NotImplementedError("Bar chart transformation not yet implemented")
        elif panel_config.type == "table":
            # For tables, just return the data as-is
            return {
                "type": "table",
                "title": panel_config.title,
                "data": data
            }
        else:
            raise ValueError(f"Unknown panel type: {panel_config.type}")

