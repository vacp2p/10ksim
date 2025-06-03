#!/usr/bin/env python3


import glob
import logging
import os
import shutil
import time
from typing import List, Literal, Optional, Tuple

from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator
# from ruamel import yaml
from ruamel.yaml import YAMLObject

from kube_utils import (
    assert_equals,
    cleanup_resources,
    default_chart_yaml_str,
    get_YAML,
    get_cleanup_resources,
    helm_build_dir,
    helm_build_from_params,
    kubectl_apply,
    maybe_dir,
    poll_namespace_has_objects,
    wait_for_cleanup,
    wait_for_no_objs_in_namespace,
    wait_for_rollout,
)

from ruamel.yaml.comments import CommentedMap

logger = logging.getLogger(__name__)


class WakuBuilder(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    api_client: ApiClient = Field(default=client.ApiClient())

    deployment_dir: str = Field(default=os.path.dirname(__file__))

    def _get_excluded_yamls(self, work_sub_dir, service):
        return [path for path in glob.glob(os.path.join(work_sub_dir, "templates", "*.yaml"), recursive=False)]

    def _get_values_yamls(self, work_sub_dir, service):
        """Get all *.yaml files from this experiment that should be included in `--values <values.yaml>` args.

        Make sure to add your own values.yaml passed through the CLI.
        """
        exclude_values = self._get_excluded_yamls(work_sub_dir, service)
        templates_dir = os.path.join(work_sub_dir, "templates")
        return [
            os.path.relpath(path, work_sub_dir)
            for path in glob.glob(os.path.join(templates_dir, "**", "*.yaml"), recursive=True)
            if path not in exclude_values
        ]

    def build(
        self,
        workdir: str,
        cli_values: Optional[YAMLObject],
        service: Literal["nodes", "publisher", "bootstrap"],
        extra_values_names: Optional[List[str]] = None,
        name: Optional[str] = None,
    ) -> YAMLObject:
        """

        :param cli_values: Yaml object of values.yaml passed in main CLI.
        :type cli_values: Optional[yaml.YAMLObject],

        :param extra_values_names: The names of the extra values yamls to use from the ./values/ subdirectory. Eg. ["regression.yaml"]
        :type extra_values_names: Optional[List[str]]

        """
        logger.debug(f"Building waku deployment file. Deployment type: `{service}`")
        if name is None:
            name = service
        if extra_values_names is None:
            extra_values_names = []
        if cli_values is None:
            cli_values = CommentedMap()

        work_sub_dir = os.path.join(workdir, service)
        logger.debug(f"Removing work subdir: {work_sub_dir}")
        try:
            shutil.rmtree(work_sub_dir)
        except FileNotFoundError:
            pass

        shutil.copytree(
            os.path.join(self.deployment_dir, service),
            work_sub_dir,
        )

        # TODO [error checking] Check for collision between service dir and common templates.
        shutil.copytree(
            os.path.join(self.deployment_dir, "templates"),
            os.path.join(work_sub_dir, "templates"),
            "templates",
            dirs_exist_ok=True,
        )

        values_path = os.path.join(work_sub_dir, "cli_values.yaml")
        yaml = get_YAML()
        assert not os.path.exists(
            values_path
        ), "Unexpected: cli_values.yaml already exists in template path."
        with open(values_path, "w") as out:
            yaml.dump(cli_values, out)

        # extra_values = [os.path.join(work_sub_dir, values, name) for name in extra_values_names]
        all_values = (
            self._get_values_yamls(work_sub_dir, service)
            + [os.path.join("values", name) for name in extra_values_names]
            + [os.path.relpath(values_path, work_sub_dir)] # It is significant that [values_path] is at the end.
        )

        deployment = helm_build_dir(
            workdir=work_sub_dir,
            values_paths=all_values,
            name=name,
        )

        # Dump the constructed deployment yaml for debugging/reference.
        with open(os.path.join(work_sub_dir, "out_deployment.yaml"), "w") as out:
            yaml.dump(deployment, out)

        return deployment
