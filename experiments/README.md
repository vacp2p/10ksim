# Purpose
This tool helps with setting up and running tests. Primarily, it generates deployment yamls, applies the deployments, waits for the test, and cleans up the environment based on the parameters passed in. However, it is flexible enough that it can be adapted to other workflows.

# Example usage
```
python ./main.py --values ./deployment/waku/regression/values.yaml --config ../ruby.yaml -vv regression_nodes --type waku
```
Here we use the values.yaml already in the deployment folder, which already has all the required parameters.

# Requirements
- [helm](https://helm.sh/docs/intro/install/) should be installed and in $PATH. The python code utilized `helm` in a subprocess to generate the deployment yamls.
- `pip install -r requirements.txt`

# Structure
Essentially, this script consists of several parts:
- `kube_utils.py` - A bunch of utilities for interacting with kubernetes and a few misc utilities as well.
- `main.py` - Parses common parameters, does a small amount of setup, and selects experiment type.
- `experiment/dispatch.py` - Contains the information nessesary to set up and run the experiment. This may be broken into smaller pieces, such as `regression_tests/waku.py` and `regression_tests/nimlibp2p.py`. Each experiment should contain a subparser for its own parameters and a function to run that can be selected by `main.py:run_experiment`.
