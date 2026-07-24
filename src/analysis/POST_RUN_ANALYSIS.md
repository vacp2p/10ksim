# Post-Run Analysis

This document explains the automatic analysis step that runs after an experiment
finishes. The broader analysis package layout is documented in
`src/analysis/README.md`.

## Lifecycle

`BaseExperiment.run()` controls the order:

```text
BaseExperiment.run(run_post_analysis=True)
  _setup_log_paths()
  _dump_initial_metadata()
  await _run()
  cleanup callbacks
  log run_finished
  _dump_metadata()
  run_post_analysis(self)
```

The important boundary is:

- the experiment deploys resources and logs domain events.
- `_dump_metadata()` converts those events into `metadata.json`.
- post-run analysis consumes `experiment.metadata`.
- cleanup happens before post-run analysis, so post-run code should read
  persisted logs or metrics.

Automatic post-run analysis is best-effort. If an analysis function raises, the
error is logged and suppressed after the completed experiment metadata has
already been written.

## Metadata Shape

Post-run analysis expects the deployment side to provide a stack, ie:

```python
metadata = {
    "stack": {
        "namespace": "...",
        "stateful_sets": [...],
        "nodes_per_statefulset": [...],
        "extra_fields": [...],
        "container_name": "...",
        "start_time": "...",
        "end_time": "...",
    },
    "params": {...},
    "results": {
        "complete": {"start": "...", "end": "..."},
        "discovery": {"start": "...", "end": "..."},
    },
}
```

`metadata["stack"]` is the default query configuration. `metadata["results"]`
keeps every named event window that the bridge was able to derive from
`events.log`.

## Why Bridges Exist

Experiments log events using names that make sense for that experiment:

```python
self.log_event("wait_for_clear_finished")
self.log_event("service_discovery_started")
self.log_event("service_discovery_finished")
```

Analyzers should not need to know those lifecycle names. A bridge translates
experiment-specific events into standard metadata fields that the analysis code
can use.

For service discovery, ie:

```python
class ServiceDiscovery(BaseExperiment[ExpConfig]):
    def _get_metadata(self) -> dict:
        return ServiceDiscoveryBridge().get_metadata(self.events_log_path)
```

`ServiceDiscoveryBridge` defines the useful windows:

```python
EventWindow(
    key="complete",
    start=EventBound("wait_for_clear_finished"),
    end=EventBound("service_discovery_finished"),
)
EventWindow(
    key="discovery",
    start=EventBound("service_discovery_started"),
    end=EventBound("service_discovery_finished"),
)
```

The bridge reads `events.log`, resolves those event names to timestamps, and
writes the result into metadata.

## Default Window

`EventWindowBridge` stores every configured window under `metadata["results"]`.
It also copies one selected window into `metadata["stack"]["start_time"]` and
`metadata["stack"]["end_time"]`.

The selected window is controlled by the bridge's `interval` field:

```python
class ServiceDiscoveryBridge(EventWindowBridge):
    interval = "complete"
```

With `interval = "complete"`, the default stack becomes:

```python
metadata["stack"]["start_time"] = metadata["results"]["complete"]["start"]
metadata["stack"]["end_time"] = metadata["results"]["complete"]["end"]
```

Changing the bridge interval changes the default window for post-run code that
uses `experiment.metadata["stack"]` directly.

## Multiple Windows

If one analysis needs to query more than one window, do not mutate
`experiment.metadata["stack"]` in place. Use `stack_for_window()` to create a
copy of the stack for each named window:

```python
from src.analysis.utils.stack import stack_for_window

complete_stack = stack_for_window(experiment.metadata, "complete")
discovery_stack = stack_for_window(experiment.metadata, "discovery")
```

Each returned stack has the same namespace, StatefulSets, container, and extra
fields as the default stack, but its `start_time` and `end_time` come from the
selected `metadata["results"][window_name]`.

That lets one post-run function run, for example:

- a full-experiment check over `"complete"`.
- a focused discovery-phase check over `"discovery"`.

## Post-Run Entrypoints

An experiment opts in by declaring an import string:

```python
class ConnManagerExperiment(BaseExperiment[ExpConfig]):
    post_run_analysis = "src.analysis.post_run.connmanager:run_connmanager_analysis"
```

`src.analysis.post_run_analysis.run_post_analysis()` loads that function and
calls it with the completed experiment instance.

The import string format is:

```text
module.path:function_name
```

Values such as `:analysis`, `module:`, or `module:thing:extra` are rejected by
`load_post_run_analysis()`.

## Data Pulling

Post-run functions build a stack, add source-specific fields such as the
VictoriaLogs URL, and pass it to `DataPuller`:

```python
stack = stack_for_window(experiment.metadata, "discovery")
stack["url"] = VICTORIA_LOGS_URL

puller = DataPuller().with_kwargs(stack).with_source_type("victoria")
```

For VictoriaLogs, `DataPuller` uses `start_time` and `end_time` when building
the query time filter:

```text
_time:[<start_time>, <end_time>]
```

The rest of the stack selects the namespace, container, StatefulSets, node
counts, and extra fields.

## Checklist

For a new automatic post-run analysis:

1. Log the domain events in `_run()`.
2. Add or update a bridge that maps those events to named windows.
3. Override `_get_metadata()` if the default bridge is not enough.
4. Add a post-run function under `src/analysis/post_run/`.
5. Set `post_run_analysis = "module.path:function_name"` on the experiment.
6. Build a stack from `experiment.metadata["stack"]` or `stack_for_window()`.
7. Add source-specific fields such as `url` or `reader`.
8. Build a `DataPuller`.
9. Configure and run the analyzer.
10. Check that `metadata.json` contains the expected stack and windows.
