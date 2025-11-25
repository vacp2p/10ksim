# Distributed deployer framework (Template name)

**Python Version**: 3.11.5

## Yaml config:

### General configuration
Important parameters for modifying when scrapping for simulation data.
```
general_config:
  times_names: # List of timestamps 
    - ["timestamp_init", "timestamp_end", "column_name"] # Last value is used to group data in the same spot in the plot
```
Example:
```
general_config:
  times_names:
    - [ "2024-05-15 12:31:00", "2024-05-15 12:47:00", "3K-1mgs-s-1KB" ]
    - [ "2024-05-15 13:10:00", "2024-05-15 13:30:00", "2K-1mgs-s-1KB" ]
    - [ "2024-05-15 16:34:00", "2024-05-15 16:56:00", "1K-1mgs-s-1KB" ]
```

### Scrape configuration

Scrape parameters like step, interval, and dump location:
```
scrape_config:
  $__rate_interval: "rate"
  step: "step"
  dump_location: "folder_to_dump"
```
Example:
```
scrape_config:
  $__rate_interval: "121s"
  step: "60s"
  dump_location: "test/nwaku0.32/"
```

### Metrics to scrape configuration

Important parameters for which metrics to scrape:
```
metrics_to_scrape:
  scrape_name:
    query: "query" # Query to extract data from
    extract_field: "instance" # Instance values, same as in Grafana panels
    folder_name: "folder" # This will be set inside `dump_location`
```
Example of what metrics to select:
```
metrics_to_scrape:
  libp2p_network_in:
    query: "rate(libp2p_network_bytes_total{direction='in'}[$__rate_interval])"
    extract_field: "instance"
    folder_name: "libp2p-in/"
  libp2p_network_out:
    query: "rate(libp2p_network_bytes_total{direction='out'}[$__rate_interval])"
    extract_field: "instance"
    folder_name: "libp2p-out/"
```

Important parameters for plotting:
```
plotting:
  "name_of_the_plot":
    "ignore": ["name"] # Pod names that starts with this string
    "data_points": number_of_points # 1 point per minute
    "folder": # Folders to get the data from
      - "folder_name_1"
      - "folder_name_2"
    "data": # Specific data from folder that will be used for the plot, needs to match `folder_name` from `metrics_to_scrape`
       - "data_from_folder"
    "plot_order": # Order of the plot figures, useful if we work with hashes instead of versions.
      - "73c29085"
      - "e95a94a5"
    "hue": "variable" # Values: "class" or "variable". Coloring of the figures. "variable" if we are working with only one folder. Default: "class"
    "xlabel_name": "xlabel"
    "ylabel_name": "ylabel"
    "scale-x": scale_number # If division is needed. Ie: y axis is bytes, we want KBytes, so we divide by 1000
```

Example of plotting bandwidth comparison between nWaku versions 26 27 and 28:
```
plotting:
  "bandwidth":
    "ignore": ["bootstrap", "midstrap"]
    "data_points": 25
    "folder":
      - "test/nwaku0.26/"
      - "test/nwaku0.27/"
      - "test/nwaku0.28/"
    "data":
      - "libp2p-in"
      - "libp2p-out"
    "plot_order":
      - "73c29085"
      - "e95a94a5"
    "hue": "variable"
    "xlabel_name": "NºNodes-MsgRate"
    "ylabel_name": "KBytes/s"
    "scale-x": 1000
```
We will have as many plots as keywords under `plotting`.
Inside each plot, we will have as many subplots as metrics in `data`.


### Main objectives
- [X] Automatic deployment of any P2P utils
  - [X] Waku
  - [X] Bandwidth usage per node
  - [X] Log data for analysis
### Secondary objectives
- [X] Add QoS parameter support to the 10k tool
- [X] Run further Waku protocols:
  - [X] Filter
  - [X] Lightpush
  - [X] Store
  - [X] Peer exchange


## Acknowledgment

Inspired in the [Codex](https://codex.storage/) framework https://github.com/codex-storage/cs-codex-dist-tests

**Original Authors**: 
- [Ben Bierens](https://github.com/benbierens)
- [Slava Doina](https://github.com/veaceslavdoina)
- [Shaun Orssaud](https://github.com/Shorssaud)
- [Eric Mastro](https://github.com/emizzle)