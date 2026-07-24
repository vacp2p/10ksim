# Plotting

`src/analysis/plotting` contains CSV-based plotting helpers for data dumped by
the metrics scraper or by log analyzers.

## Metrics Plots

`MetricsPlotter` expects one `PlotConfig` per output image. Each config names:

- `folder`: one or more root folders that contain metric subfolders.
- `data`: metric subfolders to plot, for example `libp2p-in` or `libp2p-out`.
- `include_files`: CSV basenames to include from each metric folder.
- display options such as labels, scaling, point count, outlier handling, and
  figure size.

The expected input layout is:

```text
ExperimentOrVersionFolder/
  MetricFolder/
    RunName.csv
```

Example:

```text
nimlibp2p-1.16.0/
  libp2p-in/
    yamux.csv
    quic.csv
  libp2p-out/
    yamux.csv
    quic.csv
```

The current code usually builds plot configs in Python:

```python
from pathlib import Path

from src.analysis.plotting.config import PlotConfigBuilder
from src.analysis.plotting.metrics_plotter import MetricsPlotter

plot = (
    PlotConfigBuilder(name="bandwidth-in")
    .with_metric("libp2p-in")
    .with_folders([Path("test_results/libp2p/1.16.0")])
    .with_include_files(["yamux", "quic"])
    .build()
)

MetricsPlotter(configs=[plot]).create_plots()
```

`scrape.py` uses the same API through `PlotConfigBuilder.with_data_from_scrapes`
to add freshly scraped result folders.

## Latency Plots

`LatencyPlotter` is separate from `MetricsPlotter`. It reads delivery latency
from `analysis_data/summary/received.csv`, plots a CDF per run, and can produce
percentile tables.

```python
from pathlib import Path

from src.analysis.plotting.latency_plotter import LatencyPlotConfig, LatencyPlotter

config = LatencyPlotConfig(
    name="latency",
    runs={
        "baseline": Path("runs/baseline"),
        "candidate": Path("runs/candidate"),
    },
)

LatencyPlotter(configs=[config]).create_plots()
```

If a run path points directly to a CSV, that file is used. Otherwise the plotter
looks for `analysis_data/summary/received.csv` under the run directory.
