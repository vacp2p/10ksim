# Deployments

`src/deployments` contains the experiment framework used by the top-level
`deployment.py` CLI. This package owns experiment discovery, CLI config,
Kubernetes deployment, cleanup, event logging, and metadata bridge selection.

Analysis implementation lives under `src/analysis`; deployment code should only
opt into analysis by declaring a `post_run_analysis` import string.

## Runtime Flow

```text
deployment.py
  load kubeconfig
  set the kubeconfig used by kubectl helpers
  scan src/deployments for @experiment-decorated classes
  add one CLI subcommand per registered experiment
  parse common args and experiment-specific config args
  merge --values YAML with CLI args
  instantiate the selected experiment
  await experiment.run()
```

`BaseExperiment.run()` then handles the common lifecycle:

```text
_setup_log_paths()
_dump_initial_metadata()

with out.log open:
  with cleanup stack open:
    write params event
    await _run()
    cleanup Kubernetes resources

write run_finished event
_dump_metadata()
run_post_analysis(self)
```

The experiment's `_run()` method should only do experiment work:

- build Kubernetes objects
- deploy them with `self.deploy(...)` or `self.deploy_yaml(...)`
- wait for the behavior being measured
- write domain events with `self.log_event(...)`

It should not construct analyzers directly. If the experiment needs automatic
post-run analysis, configure that through `post_run_analysis`.

## CLI

Common command shape:

```shell
uv run python deployment.py -vv \
  --config ~/.kube/config \
  --values path/to/values.yaml \
  --out-folder runs/example \
  <experiment-name> \
  --namespace <namespace>
```

Discovery:

```shell
uv run python deployment.py --help
uv run python deployment.py <experiment-name> --help
```

Shared flags:

- `--config`: kubeconfig passed to Kubernetes client setup.
- `--values`: optional YAML file used as the base experiment config.
- `--out-folder`: output folder. Relative paths are placed under
  `src/deployments/experiments/out/`.
- `-v`: repeat for more logging.
- `--namespace`: required experiment namespace.
- `--skip-check`: do not block waiting for the namespace to be empty.
- `--dry-run`: dump generated YAML and run `kubectl apply --dry-run`.

Experiment-specific flags are generated from the experiment's Pydantic config
model. CLI values override entries from `--values`.

## Package Layout

```text
registry.py                 # @experiment decorator and recursive scanner.
experiments/                # Current experiment classes and multi-run wrappers.
core/                       # BaseExperiment, bridges, events, k8s helpers.
core/configs/               # Kubernetes object config/building primitives.
waku/                       # Waku builders and bridge.
libp2p/                     # nim-libp2p builders and bridges.
logos_core/                 # Logos Core delivery experiment/builders.
shadow/                     # Shadow simulator Kubernetes builders/runtime.
pod_api_requester/          # Helper pod for in-cluster protocol API calls.
utils/                      # Parser and flattening helpers.
```

The remaining Helm helper code under `src/utils/helm_utils.py` is not imported
by active experiments in this checkout. New deployment work should use the
current object builders and `BaseExperiment` pattern.

## Adding an Experiment

1. Create a Pydantic config model for experiment parameters.
2. Subclass `BaseExperiment[YourConfig]`.
3. Decorate it with `@experiment(name="your-name")`.
4. Implement `_run()`.
5. Deploy through `self.deploy(...)` or `self.deploy_yaml(...)` so YAML dumping,
   rollout waits, and cleanup callbacks are registered.
6. Log events that describe experiment milestones. Use stable, specific names;
   bridges and analysis code depend on them.
7. Override `_get_metadata()` when the default `BaseBridge` is not enough.
8. Add `post_run_analysis = "module.path:function_name"` when automatic
   analysis exists.

Do not override `add_parser()`. Add custom non-config flags with `add_args()`;
config-model fields are exposed automatically.

## Events and Metadata

`self.log_event(...)` writes JSON lines to `events.log`. Deployment helpers also
write deployment events automatically, including StatefulSet names and replica
counts.

During `_dump_metadata()`, the experiment's `_get_metadata()` reads `events.log`
through a bridge and writes `metadata.json`.

Use `BaseBridge` when deployment-level metadata is enough. Use
`EventWindowBridge` when analysis needs named start/end windows derived from
experiment events. The detailed bridge and window-selection behavior is
documented in `src/analysis/POST_RUN_ANALYSIS.md`.

## Output Contract

Every run should produce:

- `out.log`: Python logs.
- `events.log`: lifecycle and deployment events.
- `metadata.json`: finalized metadata and serialized experiment dump.
- `deployment_yamls/`: generated Kubernetes objects.

Cleanup runs before automatic post-run analysis. Analyzers that need live pods
need a custom pre-cleanup hook or must pull data before cleanup.
