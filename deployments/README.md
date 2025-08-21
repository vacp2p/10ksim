# Purpose
This tool helps with setting up and running tests.

Primarily, it:
- Generates deployment yamls using helm
- Applies the kubernetes deployments
- Adds callbacks to ensure kubernetes deployments are always cleaned up
- Waits for the experiment to finish

However, it is flexible enough that it can be adapted to other workflows.

# Example usage
```
python ./deployment.py -vv --config ~/<kube_config>.yaml regression-nodes --type waku
```
Here we use the values.yaml already in the deployment folder, which already has all the required parameters.

> ⚠️ **Warning**
>
> For long-running experiments, make sure your computer doesn't fall asleep. A good way to do this on Mac is to use `caffeinate` like this:
>
> `caffeinate -s -m -i python ./deployment.py -vv --config ~/<kube_config>.yaml regression-nodes --type waku`


# Requirements
- [helm](https://helm.sh/docs/intro/install/) should be installed and in $PATH.
  The python code utilizes `helm` in a subprocess to generate the deployment yamls.
- `pip install -r requirements.txt`

# Pitfalls

> ⚠️ **Warning**
>
> Make sure you do not create a python virtual in this folder.
> `make format` and the `registry.py` scan will raise errors if you do.

# Structure
Essentially, this script consists of several parts:
- `kube_utils.py` - A bunch of utilities for interacting with kubernetes
                    and a few misc utilities as well.
- `deployment.py` - Parses common parameters, does a small amount of setup, and selects experiment type.
- `deployments/` - Contains experiments and helm template info

## Experiments

Experiments are gathered by `registry.py`,
which scans files looking for the `@experiment(...)` decorator.

Each experiment should contain the following functions:
###  add_parser

- def add_parser(subparsers)

- Called in `deployment` to add subparsers for CLI arguments.

### run
- def run(
        self,
        api_client: ApiClient,
        args: argparse.Namespace,
        values_yaml: Optional[yaml.YAMLObject]
    )

-  Called in `deployment.py/run_experiment` with `args` and `values_yaml`
   from CLI args and `api_client` created with the kubeconfig value from `--config`.

> 💡 **Tip**
>
> The best way to make your own experiment is to copy an existing experiment and modifying it. For example, if you want to make a new test using Waku, start with `deployment/waku/experiments/regression/`