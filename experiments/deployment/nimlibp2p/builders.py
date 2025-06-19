#!/usr/bin/env python3


import logging
import os
import shutil
from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from yaml import YAMLObject

from ruamel.yaml.comments import CommentedMap

logger = logging.getLogger(__name__)


class Nimlibp2pBuilder(BaseModel):

    deployment_dir: str = Field(default=os.path.dirname(__file__))

    def build(
        self,
        workdir: str,
        cli_values: Optional[YAMLObject],
        extra_values_names: Optional[List[str]] = None,
        name: Optional[str] = None,
    ) -> YAMLObject:
        """

        :param cli_values: Yaml object of values.yaml passed in main CLI.
        :type cli_values: Optional[yaml.YAMLObject],

        :param extra_values_names: The names of the extra values yamls to use from the ./values/ subdirectory. Eg. ["regression.yaml"]
        :type extra_values_names: Optional[List[str]]

        """
        logger.debug(f"Building libnimp2p deployment file.")
        if extra_values_names is None:
            extra_values_names = []
        if cli_values is None:
            cli_values = CommentedMap()

        work_sub_dir = os.path.join(workdir, "nimlibp2p")
        logger.debug(f"Removing work subdir: {work_sub_dir}")
        try:
            shutil.rmtree(work_sub_dir)
        except FileNotFoundError:
            pass

            # todo asdf curr
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
            + [
                os.path.relpath(values_path, work_sub_dir)
            ]  # It is significant that [values_path] is at the end.
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
