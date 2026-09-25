"""Re-run a finished run's post-run analysis from its folder."""

import argparse
import importlib
import json
import logging
from pathlib import Path

from kubernetes import config
from kubernetes.client import ApiClient

from src.analysis.post_run_analysis import run_post_analysis
from src.analysis.utils.log_utils import init_logger
from src.deployments.core.k8s_kubeconfig import set_config_file
from src.deployments.experiments.base_experiment import BaseExperiment, experiment_from_metadata

logger = logging.getLogger(__name__)


def rebuild(run: Path, api_client: ApiClient) -> BaseExperiment:
    metadata = json.loads((run / "metadata.json").read_text())
    dump = metadata["experiment"]["dump"]
    importlib.import_module(dump["_type"].rpartition(".")[0])
    # Point the paths at the folder as it is now, in case it was moved.
    dump |= {
        "output_folder": str(run),
        "events_log_path": str(run / "events.log"),
        "metadata_log_path": str(run / "metadata.json"),
        "skip_check": True,
    }
    return experiment_from_metadata(api_client, metadata)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", help="Run folders holding a metadata.json")
    parser.add_argument("--config", default=str(Path.home() / ".kube/config"), help="Kube config")
    args = parser.parse_args()
    init_logger(logging.getLogger(), verbosity=1)
    config.load_kube_config(config_file=args.config)
    set_config_file(args.config)
    api_client = ApiClient()
    for arg in args.runs:
        run = Path(arg).resolve()
        logger.info(f"Re-running post-run analysis for {run}")
        run_post_analysis(rebuild(run, api_client))


if __name__ == "__main__":
    main()
