# Experiment Deployment & Analysis Toolkit

## Overview
This repository contains internal tools for running, managing, and analyzing experiments on distributed systems.
It is currently used to:
- Launch experiments on Kubernetes clusters
- Collect metrics and logs from previously run experiments
- Analyze experiment metrics (e.g., bandwidth analysis, message reliability, message latency, etc.)

These tools were originally designed to test scalability for nim-libp2p and Waku, but adaptable for a wide variety of experiments.

Note: This is a work in progress. Tooling and folder structure may change in the future.

---

## Dependencies

### uv

Install [uv](https://docs.astral.sh/uv/#installation) and just run:
```shell
uv sync
```
Required python version will be installed if not present in the system, alongside with the necessary requirements.

## Repository Structure

```
analysis/
  ├── scrape.py               # Scrape tool
  ├── example_log_analysis.py # Analysis tool
  ├── scrape.yaml             # Scrape config
deployment/
  ├── docker_utilities/       # Dockerfiles & resources to build experiment containers
  ├── kubernetes-utilities/   # Services required on Kubernetes for certain experiments
  ├── experiment_scripts/     # Legacy bash scripts for deployments
experiments/
  ├── deployment.py           # Experiment deployment script (generates & deploys)
  ├── README.md               # Usage guide for deployment script
```

---

### `./experiments/`
Python scripts and Kubernetes templates for generating deployments and running experiments.

`deployment.py`:
- Generates Kubernetes manifests for experiments
- Deploys them to the cluster
- Automatically cleans up resources on completion or abort

See `./experiments/README.md` for usage instructions.

---

### `./analysis/`
Tools for scraping metrics and analyzing results.

#### Scraping
`scrape.py`:
- Queries metric sources and creates plots.
- Metrics to scrape and plots to generate are defined in `scrape.yaml`

#### Analysis
`log_analysis.py`
- Processes scraped data
- Further analyses (eg. check that messages appear in store nodes)
- Generates plots (eg. message time distribution plots)

---

## Typical Workflow

1. Run an experiment
   ```
   cd experiments
   python ./deployment.py --config ~/sapphire.yaml waku-regression-nodes --workdir ./workdir
   ```

2. Scrape data from the finished experiment
   ```
   cd analysis
   python3 scrape.py
   ```

3. Analyze results
   ```
   python3 log_analysis.py
   ```
