import asyncio
import logging
import random
import traceback
from abc import abstractmethod
from argparse import Namespace
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from datetime import timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict
from ruamel import yaml

from src.deployments.core.kube_utils import dict_set
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.registry import experiment
from src.deployments.registry import registry as experiment_registry

logger = logging.getLogger(__name__)


def dict_to_namespace(dictionary: dict):
    if isinstance(dictionary, dict):
        return SimpleNamespace(
            **{key: dict_to_namespace(value) for key, value in dictionary.items()}
        )
    return dictionary


@experiment(name="multi")
class Multiple(BaseExperiment, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    experiment_name: Optional[str] = None
    delay_between_exps: Optional[float] = None

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="Run an experiment multiple times with different parameters."
        )
        Multiple.add_args(subparser)
        BaseExperiment.add_args(subparser)

    @classmethod
    def add_args(cls, subparser) -> None:
        subparser.add_argument(
            "--name", type=str, required=False, help="Name of the experiment to run."
        )
        subparser.add_argument(
            "--delay",
            type=Optional[float],
            required=False,
            default=None,
            help="Delay (in seconds) between each experiment run.",
        )

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        logger.info("Multiple experiments")
        param_list = self.get_params_list()
        self.delay_between_exps = args.delay or self.delay_between_exps
        assert (
            self.delay_between_exps
        ), "delay_between_exps must be specified either in the subclass or the cli args (--delay)"
        for params in param_list:
            this_time = datetime.now(dt_timezone.utc)
            logger.info(f"UTC time: {this_time.hour:02d}:{this_time.minute:02d}")

            params_str = self.get_name_from_params(params)

            # Adding a random number helps distinguish experiments.
            random_number = random.randint(1, 200000)
            exp_workdir = Path(workdir) / f"{params_str}__rand_{random_number}"

            exp_values_yaml = deepcopy(values_yaml)
            for key, value in params.items():
                dict_set(exp_values_yaml, key, value, sep=".", replace_leaf=True)

            exp_args = deepcopy(args)
            exp_args.workdir = exp_workdir
            exp_args.output_folder = exp_workdir

            exp_name = self.experiment_name
            if args.name:
                exp_name = args.name
            if not exp_name:
                raise ValueError("Missing name of experiment to run.")

            info = experiment_registry[exp_name]
            experiment = info.cls()
            logger.info(
                f"Running experiment. name `{info.name}` file: `{info.metadata['module_path']}`"
            )
            try:
                await experiment.run(api_client, exp_args, exp_values_yaml)
            except Exception as e:
                logger.error(f"Experiment failed. Exception: {e} {traceback.format_exc()}")

            logger.info(f"sleeping {self.delay_between_exps} between experiments")
            await asyncio.sleep(self.delay_between_exps)

    @abstractmethod
    def get_params_list(self) -> List[dict]:
        """Return list of param sets.
        Each param set is a dict with `key` : `value`,
        where `key` is mapped to the values.yaml using the `get_params_paths()`."""
        raise NotImplementedError("Implement in derived class.")

    def get_name_from_params(self, params: dict) -> str:
        param_list = [f"{key}_{value}" for key, value in params.items()]
        return "__".join(param_list)
