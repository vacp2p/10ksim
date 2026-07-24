# Mesh Analysis

`mesh_analysis` provides reusable log-analysis building blocks for protocol
experiments. It does not decide which experiment window to analyze; callers pass
an already-built stack through `DataPuller`.

## Structure

```text
analyzers/
  analyzer.py               # AnalysisStep, AnalysisResult, Analyzer base class.
  data_puller.py            # Source selection: VictoriaLogs or local files.
  *_analyzer.py             # Domain checks for Waku, nim-libp2p, connmanager, etc.
readers/
  reader.py                 # Reader base class.
  victoria_reader.py        # VictoriaLogs-backed log reader.
  file_reader.py            # Local log-file reader.
  tracers/                  # Log-line parsers for message, service discovery, etc.
  builders/                 # Reader builders.
stacks/
  stack_analysis.py         # Stack-level data retrieval contract.
  vaclab_stack_analysis.py  # VictoriaLogs/Vaclab implementation.
  file_stack_analysis.py    # Local-file implementation.
images/                     # Documentation assets.
```

## Data Flow

Callers provide stack metadata and a source type:

```python
puller = DataPuller().with_kwargs(stack).with_source_type("victoria")
```

The analyzer receives the puller and configures checks:

```python
results = (
    ServiceDiscoveryAnalyzer(dump_analysis_dir=experiment.output_folder / "analysis_data")
    .with_data_puller(puller)
    .with_discovery_analysis()
    .run()
)
```

The key pieces are:

- `DataPuller`: chooses a source and creates the right stack/reader.
- `StackAnalysis`: coordinates data retrieval for a deployment environment.
- `Reader`: fetches raw log lines from VictoriaLogs or local files.
- `Tracer`: parses raw log lines into structured rows.
- `Analyzer`: composes checks and returns `AnalysisResult` objects.

For VictoriaLogs, stack metadata usually includes `url`, `start_time`,
`end_time`, `namespace`, `container_name`, `stateful_sets`,
`nodes_per_statefulset`, and `extra_fields`.

For local Shadow logs, use `DataPuller().with_local(path_to_logs)`.

## Adding or Updating Checks

1. Add or update a tracer when the raw log-line format changes.
2. Keep data retrieval in readers/stacks, not inside analyzer checks.
3. Add analyzer methods that append named `AnalysisStep`s.
4. Return `AnalysisResult` with useful `intermediates` for debugging and plots.
5. Add focused tests with representative log lines or DataFrame inputs.

Analyzer steps default to continuing after failures. Use `on_fail="stop"` only
when later checks would be misleading without the earlier result.

## Troubleshooting

No rows usually means the metadata window, namespace, container name, or
StatefulSet names do not match the logs. Check `metadata.json` and the stack
passed to `DataPuller` before changing the analyzer.

Parser errors usually mean a tracer no longer matches the current application
log format. Update the tracer and add a focused test.
