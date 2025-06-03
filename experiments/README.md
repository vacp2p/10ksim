# Purpose
This tool helps with setting up and running tests.

Primarily, it:
- Generates deployment yamls.
- Applies the deployments.
- Waits for the test.
- Cleans up the environment based on the parameters passed in.

However, it is flexible enough that it can be adapted to other workflows.

# Example usage
```
python ./main.py -vv --config ~/sapphire.yaml regression-nodes --type waku --workdir ./workdir
```
Here we use the values.yaml already in the deployment folder, which already has all the required parameters.

# Requirements
- [helm](https://helm.sh/docs/intro/install/) should be installed and in $PATH.
  The python code utilized `helm` in a subprocess to generate the deployment yamls.
- `pip install -r requirements.txt`

# Pitfalls

Make sure you do not create a python virtual in this folder.
`make format` and the `registry.py` scan will raise errors.

# Structure
Essentially, this script consists of several parts:
- `kube_utils.py` - A bunch of utilities for interacting with kubernetes
                    and a few misc utilities as well.
- `main.py` - Parses common parameters, does a small amount of setup, and selects experiment type.
- `deployments/` - Contains experiments and helm template info

## Experiments

Experiments are gathered by `registry.py`,
which scans files looking for the `@experiment(...)` decorator.

Each experiment should contain the following functions:
###  add_parser

- def add_parser(subparsers)

- Called in `main` to add subparsers for CLI arguments.

### run
- def run(
        self,
        api_client: ApiClient,
        args: argparse.Namespace,
        values_yaml: Optional[yaml.YAMLObject]
    )

-  Called in `main.py/run_experiment` with `args` and `values_yaml`
   from CLI args and `api_client` created with the kubeconfig value from `--config`.



