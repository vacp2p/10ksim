import logging
import os
from pathlib import Path
import shutil
from typing import List, Literal, Optional

from kubernetes import client
from kubernetes.client import ApiClient
from pydantic import BaseModel, ConfigDict, Field

from ruamel.yaml import YAMLObject
from ruamel.yaml.comments import CommentedMap

from kube_utils import get_values_yamls, get_YAML, helm_build_dir

logger = logging.getLogger(__name__)


def build_deployment(
    deployment_dir: str,
    workdir: str,
    cli_values: Optional[YAMLObject],
    name: str,
    extra_values_names: Optional[List[str]] = None,
    extra_values_paths: Optional[List[str]] = None,
) -> YAMLObject:
    """

    :param deployment_dir: Root directory of deployment. Eg. `.../deployments/waku/nodes`:
    :type deployment_dir: str

    :param cli_values: Yaml object of values.yaml passed in main CLI.
    :type cli_values: Optional[yaml.YAMLObject],

    :param extra_values_names: The names of the extra values yamls to use from the ./values/ subdirectory. Eg. ["regression.values.yaml"]
    :type extra_values_names: Optional[List[str]]

    """
    logger.debug(f"Building deployment file from dir: {deployment_dir} -> {workdir}")
    if extra_values_names is None:
        extra_values_names = []
    if extra_values_paths is None:
        extra_values_paths = []
    if cli_values is None:
        cli_values = CommentedMap()
    name = name.replace('_', '-')

    logger.debug(f"Removing work dir: {workdir}")
    try:
        shutil.rmtree(workdir)
    except FileNotFoundError:
        pass

    shutil.copytree(
        os.path.join(deployment_dir),
        workdir,
    )

    # TODO [error checking] Check for collision between service dir and common templates.
    common_templates_dir = os.path.join(deployment_dir, "..", "templates")
    try:
        shutil.copytree(
            common_templates_dir,
            os.path.join(workdir, "templates"),
            dirs_exist_ok=True,
        )
    except FileNotFoundError:
        pass # Common templates path doesn't exist.

    # Copy in external .values.yaml files.
    external_values_dir = os.path.join(workdir, "values", "experiment")
    os.makedirs(external_values_dir,exist_ok=True)
    include_extras = []
    for extra in extra_values_paths:
        shutil.copy(extra, external_values_dir)
        include_extras.append(os.path.join("values", "experiment", Path(extra).name))

    values_path = os.path.join(workdir, "cli_values.yaml")
    yaml = get_YAML()
    assert not os.path.exists(
        values_path
    ), "Unexpected: cli_values.yaml already exists in template path."
    with open(values_path, "w") as out:
        yaml.dump(cli_values, out)

    all_values = (
        get_values_yamls(workdir)
        + [os.path.join("values", name) for name in extra_values_names]
        + include_extras
        + [
            os.path.relpath(values_path, workdir)
        ]  # Being at the end gives [values_path] the highest priority.
    )

    deployment = helm_build_dir(
        workdir=workdir,
        values_paths=all_values,
        name=name,
    )

    # Dump the constructed deployment yaml for debugging/reference.
    with open(os.path.join(workdir, "out_deployment.yaml"), "w") as out:
        yaml.dump(deployment, out)

    return deployment


def build_deployment_type(
    deployment_dir: str,
    workdir: str,
    cli_values: Optional[YAMLObject],
    service: str,
    name: Optional[str] = None,
    extra_values_names: Optional[List[str]] = None,
) -> YAMLObject:
    """

    :param deployment_dir: Root directory of deployment type. Eg. `.../deployments/waku/`:
    :type deployment_dir: str

    :param cli_values: Yaml object of values.yaml passed in main CLI.
    :type cli_values: Optional[yaml.YAMLObject],

    :param extra_values_names: The names of the extra values yamls to use from the ./values/ subdirectory. Eg. ["regression.values.yaml"]
    :type extra_values_names: Optional[List[str]]

    """
    logger.debug(f"Building deployment file. Deployment type: `{service}`")
    if name is None:
        name = service
    if extra_values_names is None:
        extra_values_names = []
    if cli_values is None:
        cli_values = CommentedMap()

    return build_deployment(
        deployment_dir=os.path.join(deployment_dir, service),
        workdir=os.path.join(workdir, service),
        cli_values=cli_values,
        name=name,
        extra_values_names=extra_values_names,
    )
