# Post-Run Analysis

This document explains the part of an experiment that happens after the experiment body has run: metadata generation, bridge usage, stack configuration, data pulling, and analyzer execution.

## Lifecycle

Experiment behavior lives in `BaseExperiment.run()`.

The current order is:

```text
BaseExperiment.run()
  _setup_log_paths()
  _dump_initial_metadata()

  with log_to_path(out.log):
    with ExitStack():
      log params metadata
      await _run()
      register cleanup_start
    cleanup callbacks run here

  log run_finished
  _dump_metadata()
  run_post_analysis(self)
```

The important rule is: `_run()` should perform the experiment and log domain events. Post-run analysis should consume finalized metadata and run analyzers from `src.analysis`, outside the experiment class.

Do not call analyzers from inside `_run()` unless there is a specific reason to analyze before normal metadata finalization.

Post-run analysis is best-effort during an experiment run. If the configured analysis reference cannot be loaded, or if the analysis function raises, `run_post_analysis()` logs the exception with the experiment type, analysis reference, metadata path, and output folder, then returns `None`. The completed experiment remains completed. Calling `run_post_analysis()` before `experiment.metadata` exists is still a lifecycle error and raises `ValueError`.

This PR wires this flow for:

- `ConnManagerExperiment`
- `ShadowGossipsubExperiment`

Other existing experiments can be migrated in follow-up changes by adding a `post_run_analysis` class attribute and moving analyzer construction under `src/analysis/post_run/`.

## What `_run()` Should Do

`_run()` should:

- deploy Kubernetes objects
- wait for the protocol behavior being measured
- log lifecycle events that the bridge can turn into time windows
- avoid building analysis stack dictionaries directly
- avoid calling analyzers directly

Example:

```python
async def _run(self):
    self.log_event("run_start")

    image = Image(repo=self.config.image_repo, tag=self.config.image_tag)

    await self._deploy_bootstrap(image)
    await self._deploy_popular_advertisers(image)
    await self._deploy_rare_advertiser(image)
    await self._deploy_popular_discoverer(image)

    self.log_event("service_discovery_started")
    await self._deploy_rare_discoverer(image)

    await asyncio.sleep(60)
    self.log_event("service_discovery_finished")
```

The event names matter. They must match the bridge that parses `events.log`.

## Metadata

At the end of `run()`, `_dump_metadata()` calls `_get_metadata()` and writes `metadata.json`.

It also assigns:

```python
self.metadata = self._get_metadata()
```

That means post-run analysis should use `experiment.metadata`, not call `_get_metadata()` again.

The standard metadata shape expected by analysis is:

```python
{
    "stack": {
        "stateful_sets": [...],
        "nodes_per_statefulset": [...],
        "namespace": "...",
        "extra_fields": [...],
        "name": "...",
        "start_time": "...",
        "end_time": "...",
        "container_name": "...",
    },
    "experiment": {
        "name": "...",
        "class": "...",
        "bridge_class": {...},
    },
    "params": {...},
    "results": {
        "complete": {"start": "...", "end": "..."},
        "discovery": {"start": "...", "end": "..."},
    },
}
```

`BaseBridge` builds most of `stack` automatically from deployment events:

- `stateful_sets`
- `nodes_per_statefulset`
- `namespace`
- `extra_fields`
- `name`
- `params`
- experiment name and class

`EventWindowBridge` adds:

- `results`
- `stack.start_time`
- `stack.end_time`
- `stack.container_name`

## Bridges

`src.deployments.core.event_window_bridge.EventWindowBridge` translates raw experiment events into standard metadata.

For example, a service discovery bridge may map:

```text
wait_for_clear_finished       -> complete.start
service_discovery_finished    -> complete.end
service_discovery_started     -> discovery.start
service_discovery_finished    -> discovery.end
```

Then the bridge chooses one interval for the default analysis window:

```python
metadata["stack"]["start_time"] = events[self.interval]["start"]
metadata["stack"]["end_time"] = events[self.interval]["end"]
```

If a bridge expects `service_discovery_finished`, then `_run()` must log exactly `service_discovery_finished`. A different event name like `finish experiment` will not match.

Use separate bridges or bridge configurations when experiments have different lifecycle semantics. Do not force unrelated experiments to use message-publishing events such as `start_messages` or `publisher_messages_finished`.

Example bridge:

```python
class ServiceDiscoveryBridge(EventWindowBridge):
    interval = "complete"
    container_name = LIBP2P_CONTAINER_NAME

    def event_windows(self):
        return [
            EventWindow(
                key="complete",
                start=EventBound("wait_for_clear_finished"),
                end=EventBound("service_discovery_finished"),
            ),
            EventWindow(
                key="discovery",
                start=EventBound("service_discovery_started"),
                end=EventBound("service_discovery_finished"),
            ),
        ]
```

## Post-Run Registry

`BaseExperiment.run()` delegates to `src.analysis.post_run_analysis.run_post_analysis(self)` after metadata is dumped. Experiments do not override a post-run hook. Instead, an experiment may declare a post-run analysis import string that points to a function in `src.analysis`.

Example:

```python
from typing import ClassVar


class ConnManagerExperiment(BaseExperiment[ExpConfig]):
    post_run_analysis: ClassVar[str] = (
        "src.analysis.post_run.connmanager:run_connmanager_analysis"
    )
```

The analysis function stays outside the experiment:

```python
def run_connmanager_analysis(experiment):
    stack = dict(experiment.metadata["stack"])
    stack["url"] = "https://vlselect.lab.vac.dev/select/logsql/query"
    stack["reader"] = "victoria"

    puller = DataPuller().with_kwargs(stack).with_source_type("victoria")

    analyzer = (
        ConnManagerAnalyzer(
            dump_analysis_dir=experiment.output_folder / "deployment_yamls" / "analysis_data"
        )
        .with_data_puller(puller)
        .with_hub_analysis(hub_pod="hub-0")
    )

    analyzer.run()
```

Use `dict(experiment.metadata["stack"])` so analysis-specific additions like `url` do not mutate the stored metadata unexpectedly.

The import string must contain exactly one `:` and both parts must be non-empty:

```text
module.path:function_name
```

Malformed values such as `:analysis`, `module:`, or `module:thing:extra` are rejected by `load_post_run_analysis()` with `ValueError`.

## Data Puller

`DataPuller` receives the stack metadata and decides how logs are retrieved.

For VictoriaLogs, required stack keys are normally:

- `url`
- `start_time`
- `end_time`
- `namespace`
- `container_name`
- `stateful_sets`
- `nodes_per_statefulset`
- `extra_fields`

The Victoria query builder uses these fields to filter logs:

```text
kubernetes.container_name:<container_name>
kubernetes.pod_namespace:<namespace>
_time:[<start_time>, <end_time>]
kubernetes.pod_name:<stateful_set>-<index>
```

If analysis returns no data, first check the generated metadata window and the container name.

## Analyzer

Analyzers are built from small checks.

Typical pattern:

```python
analyzer = (
    SomeAnalyzer(dump_analysis_dir=self.output_folder / "analysis_data")
    .with_data_puller(puller)
    .with_some_check()
    .with_another_check()
)

results = analyzer.run()
```

Each check returns an `AnalysisResult` with:

- `name`
- `status`: `passed`, `failed`, `skipped`, or `error`
- `intermediates`: debug or result details

If a step is configured with `on_fail="stop"`, analyzer execution raises when that check fails or errors.
When the analyzer is invoked through automatic post-run analysis, that exception is logged and suppressed by `run_post_analysis()` after the completed experiment metadata has already been written.

## Cleanup Timing

In the current lifecycle, cleanup callbacks run before `_dump_metadata()` and `run_post_analysis()`.

That is fine for analysis that reads persisted logs from VictoriaLogs. It is not fine for analysis that needs live pods or live Kubernetes API state. If an analyzer needs live objects, it should run before the `ExitStack` exits or use a different hook.

## Common Failures

`events[self.interval]["end"]` fails:

- the bridge interval is wrong, or
- `_run()` did not log the event used as the interval end, or
- post-run analysis called `_get_metadata()` instead of using finalized `experiment.metadata`

No logs returned:

- `stack.start_time` / `stack.end_time` are wrong
- `stack.container_name` does not match the logged Kubernetes container
- `stack.namespace` is wrong
- `stateful_sets` or `nodes_per_statefulset` do not match deployed StatefulSets
- Victoria URL is missing or wrong

Date parsing receives a non-date string:

- the tracer output columns do not match the DataFrame columns
- the wrong column is being passed to `pd.to_datetime`

## Checklist For New Automatic Analysis

1. Add domain events to `_run()`.
2. Add or configure a bridge that maps those events to analysis windows.
3. Override `_get_metadata()` to use that bridge.
4. Add a post-run analysis function under `src/analysis/post_run/`.
5. Add `post_run_analysis = "module.path:function_name"` to the experiment class.
6. Add the Victoria URL or local data source.
7. Build a `DataPuller`.
8. Build an analyzer with explicit checks.
9. Confirm `metadata.json` contains `stack.start_time`, `stack.end_time`, `stateful_sets`, `nodes_per_statefulset`, and `container_name`.
