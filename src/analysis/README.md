# Analysis

`src/analysis` contains the code that turns completed experiment metadata,
logs, and metrics into checks, intermediate data, plots, and summaries.

The preferred path is automatic post-run analysis:

```text
BaseExperiment.run()
  _dump_metadata()
  run_post_analysis(experiment)
    load experiment.post_run_analysis
    call analysis function with the completed experiment
```

Manual scripts still exist for older workflows and ad hoc investigation.

## Layout

```text
post_run_analysis.py        # Loads module.path:function_name analysis hooks.
post_run/                   # Automatic post-run analysis entrypoints.
mesh_analysis/              # Log readers, tracers, DataPuller, analyzers.
metrics/                    # Prometheus/VictoriaMetrics scrape helpers.
plotting/                   # CSV-based plotting helpers.
data/                       # DataFrame/request/file handlers.
utils/stack.py              # Helpers for selecting metadata windows.
utils/                      # Other file, path, list, time, plot, logging helpers.
```

## Post-Run Entrypoints

Experiments opt in by declaring an import string:

```python
post_run_analysis = "src.analysis.post_run.service_discovery:run_service_discovery_analysis"
```

The referenced function receives the completed experiment instance. It should:

1. Read `experiment.metadata`.
2. Build a stack dictionary for the log/metric window to analyze.
3. Add analysis-only fields such as `url`, `reader`, or source-specific options.
4. Build a `DataPuller`.
5. Attach the puller to a domain analyzer.
6. Configure checks and call `analyzer.run()`.
7. Write analysis data or plots under `experiment.output_folder`.

Current automatic entrypoints:

- `post_run/connmanager.py`
- `post_run/service_discovery.py`
- `post_run/shadow_gossipsub.py`

`run_post_analysis()` catches and logs analysis exceptions so a completed
experiment remains completed even if analysis fails. Calling it before
`experiment.metadata` exists is a lifecycle error.

## Metadata, Windows, and Stacks

Deployment bridges write named event windows under `metadata["results"]` and
copy one default window into `metadata["stack"]`.

Example shape:

```python
metadata["results"] = {
    "complete": {"start": "...", "end": "..."},
    "discovery": {"start": "...", "end": "..."},
}

metadata["stack"]["start_time"] = metadata["results"]["complete"]["start"]
metadata["stack"]["end_time"] = metadata["results"]["complete"]["end"]
```

Post-run analysis can use the default stack directly:

```python
stack = dict(experiment.metadata["stack"])
stack["url"] = VICTORIA_LOGS_URL

puller = DataPuller().with_kwargs(stack).with_source_type("victoria")
```

When one analysis function needs to run over multiple windows, use
`stack_for_window()`:

```python
from src.analysis.utils.stack import stack_for_window

complete_stack = stack_for_window(experiment.metadata, "complete")
discovery_stack = stack_for_window(experiment.metadata, "discovery")

complete_stack["url"] = VICTORIA_LOGS_URL
discovery_stack["url"] = VICTORIA_LOGS_URL

complete_puller = DataPuller().with_kwargs(complete_stack).with_source_type("victoria")
discovery_puller = DataPuller().with_kwargs(discovery_stack).with_source_type("victoria")
```

`stack_for_window()` returns a copy of `metadata["stack"]` with
`start_time`/`end_time` replaced by the selected
`metadata["results"][window_name]` values. It does not mutate
`experiment.metadata`.

## DataPuller

`DataPuller` receives the stack and chooses how data is retrieved.

For VictoriaLogs, the stack normally needs:

- `url`
- `start_time`
- `end_time`
- `namespace`
- `container_name`
- `stateful_sets`
- `nodes_per_statefulset`
- `extra_fields`

The Victoria reader uses those values to build filters such as:

```text
kubernetes.container_name:<container_name>
kubernetes.pod_namespace:<namespace>
_time:[<start_time>, <end_time>]
kubernetes.pod_name:<stateful_set>-<index>
```

For local Shadow logs, use:

```python
DataPuller().with_local(run_dir / "shadow_logs" / "logs")
```

## Analyzer Framework

`mesh_analysis/analyzers/analyzer.py` defines:

- `AnalysisResult`: one check result with `passed`, `failed`, `skipped`, or
  `error` status.
- `AnalysisStep`: a named check and failure policy.
- `Analyzer`: a fluent base class that runs configured steps and prepares dump
  paths.

Domain analyzers live under `mesh_analysis/analyzers/`.

## Manual Helpers

- `log_multi_analysis.py` processes saved experiment metadata in batches.
- `scrape.py` builds Prometheus/VictoriaMetrics scrape configs from saved
  experiment metadata, dumps CSV files, and can create comparison plots.

Prefer automatic post-run analysis for new experiments so deployment metadata,
log windows, and analyzer configuration stay together.

See `POST_RUN_ANALYSIS.md` for the detailed lifecycle and bridge rules.
