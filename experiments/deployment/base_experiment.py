import logging
import shutil
from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from contextlib import ExitStack
from typing import Optional

from kubernetes.client import ApiClient
from pydantic import BaseModel
from ruamel import yaml
from ruamel.yaml.comments import CommentedMap

from kube_utils import maybe_dir, poll_namespace_has_objects, wait_for_no_objs_in_namespace

logger = logging.getLogger(__name__)


class BaseExperiment(ABC, BaseModel):
    """Base experiment that add an ExitStack with `workdir` to `run` and uses an internal `_run`.

    How to use:
        - Inherit from this class.
        - Call `BaseExperiment.add_args` in the child class's `add_parser`
        - Implement `_run` in the child class.
    """

    @staticmethod
    def add_args(subparser: ArgumentParser):
        subparser.add_argument(
            "--workdir",
            type=str,
            required=False,
            default=None,
            help="Folder to use for generating the deployment files.",
        )
        subparser.add_argument(
            "--skip-check",
            action="store_true",
            required=False,
            help="If present, does not wait until the namespace is empty before running the test.",
        )

    def run(
        self,
        api_client: ApiClient,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
    ):
        if values_yaml is None:
            values_yaml = CommentedMap()

        with ExitStack() as stack:
            workdir = args.workdir
            stack.enter_context(maybe_dir(workdir))
            try:
                shutil.rmtree(workdir)
            except FileNotFoundError:
                pass
            self._run(
                api_client=api_client,
                workdir=workdir,
                args=args,
                values_yaml=values_yaml,
                stack=stack,
            )

    @abstractmethod
    def _run(
        self,
        api_client: ApiClient,
        workdir: str,
        args: Namespace,
        values_yaml: Optional[yaml.YAMLObject],
        stack: ExitStack,
    ):
        pass

    def _wait_until_clear(self, api_client: ApiClient, namespace: str, skip_check: bool):
        # Wait for namespace to be clear unless --skip-check flag was used.
        if not skip_check:
            wait_for_no_objs_in_namespace(namespace=namespace, api_client=api_client)
        else:
            namepace_is_empty = poll_namespace_has_objects(
                namespace=namespace, api_client=api_client
            )
            if not namepace_is_empty:
                logger.warning(f"Namespace is not empty! Namespace: `{namespace}`")
