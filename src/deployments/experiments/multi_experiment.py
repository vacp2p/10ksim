import asyncio
import logging
import random
import traceback
from abc import abstractmethod
from copy import deepcopy
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import List, Optional

from pydantic import ConfigDict

from src.deployments.core.kube_utils import dict_set
from src.deployments.experiments.base_experiment import BaseExperiment
from src.deployments.registry import experiment
from src.deployments.registry import registry as experiment_registry

logger = logging.getLogger(__name__)


@experiment(name="multi")
class Multiple(BaseExperiment):
    """Runs a registered experiment N times with different params.

    Subclasses set `experiment_name` and implement `get_params_list()`.
    See `multi_nimlibp2p.py` for a worked example.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    experiment_name: Optional[str] = None
    delay_between_exps: float = 120.0

    @classmethod
    def add_parser(cls, subparsers) -> None:
        subparser = subparsers.add_parser(
            cls.name, help="Run an experiment multiple times with different parameters."
        )
        BaseExperiment.add_args(subparser)

    @classmethod
    def add_args(cls, subparser) -> None:
        # No-op. Kept so existing subclasses calling Multiple.add_args() don't break.
        pass

    def log_event(self, event):
        logger.info(event)
        return super().log_event(event)

    async def _run(self):
        logger.info("Multiple experiments")
        param_list = self.get_params_list()

        if not self.experiment_name:
            raise ValueError(
                "experiment_name must be set on the Multiple subclass "
                "(e.g. `experiment_name = MyExperiment.name`)"
            )

        base_values = self.config if isinstance(self.config, dict) else {}

        for params in param_list:
            this_time = datetime.now(dt_timezone.utc)
            logger.info(f"UTC time: {this_time.hour:02d}:{this_time.minute:02d}")

            params_str = self.get_name_from_params(params)
            random_number = random.randint(1, 200000)
            exp_workdir = self.output_folder / f"{params_str}__rand_{random_number}"

            exp_values_yaml = deepcopy(base_values)
            for key, value in params.items():
                dict_set(exp_values_yaml, key, value, sep=".", replace_leaf=True)

            info = experiment_registry[self.experiment_name]
            child = info.cls(
                api_client=self.api_client,
                config=exp_values_yaml,
                namespace=self.namespace,
                output_folder=exp_workdir,
                skip_check=self.skip_check,
                dry_run=self.dry_run,
            )
            logger.info(
                f"Running experiment. name `{info.name}` file: `{info.metadata['module_path']}`"
            )
            try:
                await child.run()
            except Exception as e:
                logger.error(f"Experiment failed. Exception: {e} {traceback.format_exc()}")

            logger.info(f"sleeping {self.delay_between_exps}s between experiments")
            await asyncio.sleep(self.delay_between_exps)

    @abstractmethod
    def get_params_list(self) -> List[dict]:
        """Return list of param sets.
        Each param set is a dict with `key` : `value`,
        where `key` is mapped into the child's values_yaml via dict_set."""
        raise NotImplementedError("Implement in derived class.")

    def get_name_from_params(self, params: dict) -> str:
        param_list = [f"{key}_{value}" for key, value in params.items()]
        return "__".join(param_list)
