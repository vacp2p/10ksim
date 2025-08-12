# Plotting configuration structure

The structure of data dumping should be the following:
```
SoftwareFolder/
  Metric/
    ExperimentFileName.csv
```
For example, we can have:
```
Waku-v0.25/
  libp2p-in/
    1000Nodes.csv
    2000Nodes.csv
Waku-v0.26/
  libp2p-in/
    1000Nodes.csv
    2000Nodes.csv
```

Configuration Example:
```yaml
plotting:
  "bandwidth_example": # <-- File name of the plot.
    "folder":  # <-- Folder to get the data from
      - "test/nwaku/" # <-- Last folder name will be used to classify the data
      - "test/nwaku0.26/"
    "data": # <-- Metrics folder to plot, inside `folder`
      - "libp2p-in" # <-- These will be used as a title in the plot
      - "libp2p-out" # <-- These will be used as a title in the plot
  "plot_2":
    "folder":
      ...
```

We will have as many plots as keywords under `plotting`.
Inside each plot, we will have as many subplots as metrics in `data`.

Note that in order to compare the experiments, the files inside `data` folders should be named equally, 
as they will be used for naming the displayed data inside each subplot.
