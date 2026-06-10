# Python Imports
import contextlib
import glob
import itertools
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Iterator, List, Optional, Tuple, Union

from ruamel import yaml

logger = logging.getLogger(__name__)


def default_chart_yaml_str(name) -> str:
    return """
    apiVersion: v2
    name: {name}
    version: 0.1.0
    description: A Helm chart for Kubernetes""".format(name=name)


def helm_build_dir(workdir: str, values_paths: List[str], name: str) -> yaml.YAMLObject:
    values = [["--values", values_path] for values_path in values_paths]
    command = ["helm", "template", ".", "--name-template", name, "--debug"] + list(
        itertools.chain(*values)
    )
    logger.info(f"Running helm template command. cwd: `{workdir}`\tcommand: `{command}`")
    logger.info(f"Usable command: `{' '.join(command)}`")
    result = subprocess.run(
        command,
        cwd=workdir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise Exception(
            f"Failed to build helm template. cwd: `{workdir}`\tcommand: `{command}`\tstderr: `{result.stderr}`"
        )

    return yaml.safe_load(result.stdout)


def helm_build(
    # list of (source_path, target_path) or (source_path)
    deployment_template_paths: Union[List[Tuple[str, str]], List[str]],
    values: Union[List[Tuple[yaml.YAMLObject, str]], List[yaml.YAMLObject]],
    workdir,
    name,
    chart_yaml=None,
) -> yaml.YAMLObject:
    """
    :deployment_template_paths: list of (source_path, target_path) or (source_path).
    `target_path` is relative to workdir/templates/ (eg. workdir/templates/<target_path>).

    :values: list of (values.yaml, target_path) or (values.yaml).
    `target_path` is relative to workdir/templates/ (eg. workdir/templates/<target_path>).

    :name: name to be used for `--name-template` argument in `helm` command,
    which will be used for `.Release.Name` when making the deployment template.
    """
    assert values, Exception("'patches' should have at least one patch.")

    # Process params.
    if not isinstance(values[0], tuple):
        values = [(path, f"values_{i+1}.yaml") for i, path in enumerate(values)]
    if not isinstance(deployment_template_paths[0], tuple):
        deployment_template_paths = [
            (path, f"deployment_{i+1}.yaml") for i, path in enumerate(deployment_template_paths)
        ]

    # Write files.
    os.makedirs(os.path.join(workdir, "templates"), exist_ok=True)
    for source_path, target_path in deployment_template_paths:
        shutil.copy(source_path, os.path.join(workdir, "templates", target_path))
    for path, values_yaml in values:
        with open(os.path.join(workdir, path), "w") as out:
            out.write(yaml.dump(values_yaml, Dumper=yaml.RoundTripDumper))
    with open(os.path.join(workdir, "Chart.yaml"), "w") as chart:
        chart.write(chart_yaml)

    # Build and output.
    values_paths = [value[0] for value in values]
    return helm_build_dir(workdir, values_paths, name)


def helm_build_from_params(
    template_path,
    values_yaml: yaml.YAMLObject,
    workdir: str,
    name: str = None,
) -> yaml.YAMLObject:
    """

    :name: name to be used for `--name-template` argument in `helm` command,
    which will be used for `.Release.Name` when making the deployment template.
    """
    values = [("values.yaml", values_yaml)]
    chart_yaml = default_chart_yaml_str("my-chart")
    name = name if name else "noname"
    return helm_build([template_path], values, workdir, name, chart_yaml)


def prepend_paths(base_path: str, paths: List[str]) -> List[str]:
    return [os.path.join(base_path, path) for path in paths]


def relative_paths(base_path: str, paths: List[str]) -> List[str]:
    return [
        os.path.relpath(
            os.path.join(base_path, path) if not os.path.isabs(path) else path, base_path
        )
        for path in paths
    ]


def get_values_yamls(
    work_sub_dir,
    *,
    include_default: bool = False,
    base_dir: Optional[str] = None,
    absolute_paths: bool = False,
) -> List[str]:
    """Get all *.yaml files from this experiment that should be included in `--values <values.yaml>` args.

    :param include_default: If True, includes the "values.yaml",
                            which is included by default in `helm` projects.
                            The default values.yaml will be the first value in returned list.
    :param absolute_paths: If True, return list as absolute paths. Overrides `base_dir`.
    :param base_dir: If True, return list as relative paths using `base_dir` as the root path.
    :return: A list of all relevant *.yaml files according to the options provided.
    :rtype: List[str]

    Make sure to add your own cli_values.yaml passed through the CLI.
    """
    templates_dir = os.path.join(work_sub_dir, "templates")
    paths = [
        os.path.relpath(path, work_sub_dir)
        for path in glob.glob(os.path.join(templates_dir, "**", "*.values.yaml"), recursive=True)
    ]

    if include_default:
        default_path = os.path.join(work_sub_dir), "values.yaml"
        if os.path.exists(default_path):
            paths = [default_path] + paths

    absolute_values = [os.path.join(work_sub_dir, path) for path in paths]
    if absolute_paths:
        return absolute_values

    if base_dir:
        return relative_paths(base_dir, absolute_values)

    return paths


@contextlib.contextmanager
def maybe_dir(dir: Optional[str]) -> Iterator[str]:
    if dir:
        yield dir
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir
