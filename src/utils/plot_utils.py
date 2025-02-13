# Python Imports
from matplotlib import pyplot as plt, patheffects as path_effects
from result import Result, Err, Ok

# Project Imports



def add_boxplot_stat_labels(ax: plt.Axes, fmt: str = ".3f", value_type: str = "median",
                            scale_by: float = 1.0) -> Result[None, str]:
    # Refactor from https://stackoverflow.com/a/63295846
    """
    Add text labels to the median, minimum, or maximum lines of a seaborn boxplot.

    Args:
        ax: plt.Axes, e.g., the return value of sns.boxplot()
        fmt: Format string for the value (e.g., min/max/median).
        value_type: The type of value to label. Can be 'median', 'min', or 'max'.
        scale_by: Scales the written value of the value type by this factor.
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
        return Err("Invalid value_type. Must be 'min', 'max', or 'median'.")

    for value_line in lines[line_idx::lines_per_box]:
        x, y = (data.mean() for data in value_line.get_data())
        # choose value depending on horizontal or vertical plot orientation
        value = x if len(set(value_line.get_xdata())) == 1 else y
        text = ax.text(x, y, f'{value*scale_by:{fmt}}', ha='center', va='center',
                       fontweight='bold', color='white', size=10)
        # create colored border around white text for contrast
        text.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground=value_line.get_color()),
            path_effects.Normal(),
        ])

    return Ok(None)
