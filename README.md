# 10ksim

10ksim is a Python toolkit for running distributed-system experiments on
Kubernetes and analyzing the logs or metrics produced by those runs.

At a high level:

```text
deployment.py
  -> experiment._run()
  -> events.log
  -> bridge-generated metadata.json
  -> post-run analysis
  -> analysis data and plots
```

The code is split by responsibility:

- `src/deployments/`: experiment registration, Kubernetes object generation,
  deployment, cleanup, event logging, and metadata bridges.
- `src/analysis/`: post-run analysis dispatch, metadata window selection,
  log/metric pulling, analyzers, and plotting helpers.
- `deployment-utilities/`: Docker images, Kubernetes manifests, and older
  support scripts used by specific experiments.
- `dst_dashboard/`: FastAPI and frontend app for publishing and visualizing
  experiment results.

Use the package READMEs for details:

- `src/deployments/README.md`: how experiments are discovered, configured, run,
  and cleaned up.
- `src/analysis/README.md`: how metadata is consumed by post-run analysis and
  how analysis windows are selected.
- `src/analysis/POST_RUN_ANALYSIS.md`: detailed lifecycle notes for bridges,
  metadata, `DataPuller`, and analyzer hooks.
- `dst_dashboard/README.md`: dashboard API and experiment publishing workflow.

## Setup

Install dependencies with `uv`:

```shell
uv sync
```

The project requires Python 3.11 or newer. Experiment deployment also expects
`kubectl` access to the target cluster through the kubeconfig passed with
`--config`.

## Running Experiments

The main entrypoint is `deployment.py`.

```shell
uv run python deployment.py --help
uv run python deployment.py <experiment-name> --help
```

Example:

```shell
uv run python deployment.py -vv \
  --config ~/.kube/config \
  --values path/to/values.yaml \
  --out-folder runs/service-discovery-demo \
  service-discovery \
  --namespace nimlibp2p
```

`--values` is optional. Values from YAML are merged with CLI arguments, and CLI
arguments win. If `--out-folder` is relative, it is resolved under
`src/deployments/experiments/out/`.

For long-running runs on a laptop, keep the machine awake. On macOS:

```shell
caffeinate -s -m -i uv run python deployment.py -vv --config ~/.kube/config service-discovery --namespace nimlibp2p
```

## Run Output

Each run writes:

- `out.log`: Python logs.
- `events.log`: raw lifecycle and deployment events.
- `metadata.json`: finalized stack, params, named windows, and serialized
  experiment config.
- `deployment_yamls/`: generated Kubernetes objects.
- `analysis_data/`: analyzer output, when automatic analysis runs.
- `plots/`: generated plots, when an analyzer produces them.
- `shadow_logs/`: pulled Shadow simulator output for Shadow experiments.

## Repository Structure

```text
deployment.py                     # Main experiment CLI.
scrape.py                         # Manual Prometheus/VictoriaMetrics scrape helper.
log_multi_analysis.py             # Manual batch log-analysis helper.
src/
  deployments/                    # Experiment framework and Kubernetes builders.
  analysis/                       # Post-run analysis and plotting.
  utils/                          # Shared generic helpers.
deployment-utilities/             # Docker/Kubernetes assets and legacy scripts.
dst_dashboard/                    # Experiment publishing dashboard.
```

## Development

Install the pre-push hook once:

```shell
make install-hooks
```

Format code:

```shell
make format
```

Check formatting without modifying files:

```shell
make check
```

Run tests:

```shell
uv run pytest
```

Run tests with coverage:

```shell
uv run pytest --cov=src --cov-report=term-missing
```

GitHub Actions run formatting checks and tests for pull requests targeting
`master`.
