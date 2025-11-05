from collections import defaultdict
from typing import Dict, List, Literal, Optional, SupportsIndex, Tuple, TypeVar

from kubernetes.client import (
    V1Container,
    V1ContainerPort,
    V1EnvVar,
    V1PersistentVolumeClaim,
    V1PodDNSConfig,
    V1Probe,
    V1ResourceRequirements,
    V1Volume,
    V1VolumeMount,
)
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Image(BaseModel):
    repo: str
    tag: str

    @staticmethod
    def from_str(image: str):
        repo, tag = image.split(":")
        return Image(repo=repo, tag=tag)

    def __str__(self):
        return f"{self.repo}:{self.tag}"


class Command(BaseModel):
    pre_command: Optional[str] = None
    command: str
    args: List[str | Tuple[str, str]] = []
    multiline: bool = False

    def with_pre_command(self, prefix: str, *, overwrite: bool = False):
        if self.pre_command and not overwrite:
            raise ValueError(
                f"Command already has a pre_command. Passed prefix: `{prefix}` Command: `{self}`"
            )
        self.pre_command = prefix

    def add_arg(
        self,
        arg: str | Tuple[str, str],
        *,
        on_duplicate: Literal["error", "ignore", "replace"] = "error",
    ):
        """Add arg to command.

        `on_duplicate` determines the behavior when an argument with the same key already exists.
        error: raises ValueError
        ignore: does not add the argument
        replace: replaces all instances of the argument in self.args with the single new argument passed in
        """
        self.add_args([arg], on_duplicate=on_duplicate)

    def _add_arg_error(self, arg, existing_args_map: dict):
        """
        Helper for add_args with on_duplicate == "error"
        """
        try:
            flag, _value = arg
        except ValueError:
            flag = arg
        if flag in existing_args_map:
            existing_flags = [self.args[index] for index in existing_args_map[flag]]
            raise ValueError(
                f"Command already contains flag(s). flag: `{flag}` existing_flags: {existing_flags}"
            )
        self.args.append(arg)

    def _add_arg_ignore(self, arg, existing_args_map: dict):
        """
        Helper for add_args with on_duplicate == "ignore"
        """
        try:
            flag, _value = arg
        except ValueError:
            flag = arg
        if flag not in existing_args_map:
            self.args.append(arg)

    def _add_arg_replace(self, arg, existing_args_map: dict):
        """
        Helper for add_args with on_duplicate == "replace"

        Note: This may modify `existing_args_map` for the caller.
        """
        try:
            flag, _value = arg
        except ValueError:
            flag = arg
        if flag in existing_args_map:
            self.args = [item for item in self.args if item != arg]
            # Remove from map so it won't be replaced again.
            del existing_args_map[flag]
            self.args.insert(existing_args_map[flag], arg)
        else:
            self.args.append(arg)

    def add_args(
        self,
        args: List[str | Tuple[str, str]] | Dict[str, str],
        *,
        on_duplicate: Literal["error", "ignore", "replace"] = "error",
    ):
        """Add args to command.

        `on_duplicate` determines the behavior when an argument with the same key already exists.

        `"error"`: raises ValueError if flag existed in self.args when this function was called

        Note: This allows you to have duplicate flags in `args` param and add them to self.args.

        `"ignore"`: does not add the argument

        `"replace"`: replaces all instances of the argument in self.args with all new arguments with the same flag

        Note: This allows you to pass in a new set of flags/value pairs to replace an existing set.

        For example: --name=Alice --name=Bob can be replaced with --name=Alfred --name=Ben --name=Carl
        """
        if isinstance(args, dict):
            args = [(key, value) for key, value in args.items()]

        existing_args_map = defaultdict(list)
        for index, arg in enumerate(self.args):
            existing_args_map[arg].append(index)

        for arg in args:
            if on_duplicate == "error":
                self._add_arg_error(arg, existing_args_map)
            elif on_duplicate == "ignore":
                self._add_arg_ignore(arg, existing_args_map)
            elif on_duplicate == "replace":
                self._add_arg_replace(arg, existing_args_map)
            else:
                raise ValueError(f"Unknown value for argument. on_duplicate: `{on_duplicate}`")

    def __str__(self) -> str:
        args = []
        for arg in self.args:
            if isinstance(arg, str):
                args.append(arg)
            else:
                args.append(f"{arg[0]}={arg[1]}")

        if not args:
            return self.command

        prefix = f"{self.pre_command} " if self.pre_command is not None else ""
        if self.multiline:
            args = [f"  {_arg}" for _arg in args]
            return f"{prefix}{self.command} \\\n" + " \\\n".join(args)
        else:
            return f"{prefix}{self.command} " + " ".join(args)


class CommandNotFoundError(ValueError):
    pass


class CommandConfig(BaseModel):
    commands: List[Command] = []

    single_k8s_command: bool = False
    """When True, then uses the Kubernetes fields "command" and "args"
    instead of a script with each command when building.

    Requires that there is only a single command.
    """

    def use_single_command(self, single_k8s_command: bool = True):
        self.single_k8s_command = single_k8s_command

    def with_commands(
        self,
        commands: List[str | Command],
        *,
        index: Optional[SupportsIndex] = None,
    ):
        """Insert multiple commands starting at a given index.

        :param commands: List of commands to insert. `str` commands are assumed to have no args.

        :param index: Starting position. If None, appends all commands to the end."""
        indices = (
            [position for position in range(index, len(commands))]
            if index is not None
            else [None for _ in range(len(commands))]
        )
        for insert_index, command in zip(indices, commands):
            if isinstance(command, Command):
                self.commands.insert(insert_index, command)
            else:
                self.with_command(command, None, multiline=False, index=insert_index)

    def with_command(
        self,
        command: str,
        args: None | List[str | Tuple[str, Optional[str]]],
        *,
        multiline: bool = False,
        index: Optional[SupportsIndex] = None,
    ):
        if args is None:
            args = []
        if index is None:
            index = len(self.commands)
        self.commands.insert(index, Command(command=command, args=args, multiline=multiline))

    _sentinel = object()

    def find_command(self, command_name: str) -> Command | None:
        """Finds the Command for the given command in the ContainerConfig"""
        result = next(
            (command for command in self.commands if command.command == command_name),
            None,
        )
        if result is CommandConfig._sentinel:
            raise CommandNotFoundError(
                f"Failed to find command in config. name: `{command_name}` config: `{self}`"
            )
        return result


class ContainerConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    command_config: CommandConfig = CommandConfig()
    readiness_probe: Optional[V1Probe] = None
    volume_mounts: Optional[List[V1VolumeMount]] = None
    resources: Optional[V1ResourceRequirements] = None
    env: Optional[List[V1EnvVar]] = None
    name: str
    image: Optional[Image] = None
    ports: Optional[List[V1ContainerPort]] = None
    image_pull_policy: Literal["IfNotPresent", "Always", "Never"]

    def with_resources(self, resources: V1ResourceRequirements, *, overwrite=False):
        if self.resources is not None and not overwrite:
            raise ValueError("Resources already exist for container")
        self.resources = resources

    def with_volume_mount(self, mount: V1VolumeMount):
        if self.volume_mounts is None:
            self.volume_mounts = []
        self.volume_mounts.append(mount)

    def with_env_var(self, var: V1EnvVar, allow_duplicates=False):
        if self.env is None:
            self.env = []
        if any([item.name == var.name for item in self.env]):
            raise ValueError(f"Attempt to add duplicate environment variable: `{var}`")
        self.env.append(var)

    def with_readines_probe(self, readiness_probe: V1Probe | dict, overwrite=False):
        from builders.helpers import dict_to_v1probe

        if self.readiness_probe is not None and overwrite == False:
            raise ValueError("ContainerConfig already has readiness probe.")
        if isinstance(readiness_probe, dict):
            readiness_probe = dict_to_v1probe(readiness_probe)
        self.readiness_probe = readiness_probe


class PodSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    volumes: Optional[List[V1Volume]] = None
    init_containers: Optional[List[ContainerConfig]] = None
    container_configs: List[ContainerConfig] = []
    dns_config: Optional[V1PodDNSConfig] = None

    def with_dns_service(self, service: str):
        if self.dns_config is None:
            self.dns_config = V1PodDNSConfig(searches=[])
        self.dns_config.searches.append(service)

    def with_volume(self, volume: V1Volume):
        if self.volumes is None:
            self.volumes = []
        self.volumes.append(volume)

    def add_init_container(self, init_container: ContainerConfig | V1Container | dict):
        from builders.helpers import convert_to_container_config

        container_config = convert_to_container_config(init_container)
        if self.init_containers is None:
            self.init_containers = []
        self.init_containers.append(container_config)

    def add_container(
        self,
        container: ContainerConfig | V1Container | dict,
        *,
        order: Literal["prepend", "append"] = "append",
    ):
        from builders.helpers import convert_to_container_config

        container_config = convert_to_container_config(container)
        if order == "append":
            self.container_configs.append(container_config)
        elif order == "prepend":
            self.container_configs.insert(0, container_config)
        else:
            raise ValueError(f"Invalid order. order: `{order}`")


class PodTemplateSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    labels: Dict[str, str] = None
    pod_spec_config: PodSpecConfig = PodSpecConfig()

    def with_app(self, app):
        if self.labels is None:
            self.labels = {}
        self.labels["app"] = app


class StatefulSetSpecConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    replicas: Optional[int] = 1
    selector_labels: Optional[Dict[str, str]] = None
    service_name: Optional[str] = None
    pod_template_spec_config: PodTemplateSpecConfig = PodTemplateSpecConfig()
    volume_claim_templates: Optional[List[V1PersistentVolumeClaim]] = None

    def with_service_name(self, service_name: str, overwrite: bool = False):
        if self.service_name is not None and not overwrite:
            raise ValueError(
                f"Service name already set. Passed service_name `{service_name}` Config: `{self}`"
            )
        self.service_name = service_name

    def with_app(self, app: str, overwrite: bool = False):
        if self.selector_labels is not None and not overwrite:
            if app in self.selector_labels:
                raise ValueError(
                    f"Config already has app in selector labels. Passed app`{app}` Config: `{self}`"
                )
        if self.selector_labels is None:
            self.selector_labels = {}
        self.selector_labels["app"] = app


class StatefulSetConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: Optional[str] = None
    namespace: Optional[str] = None
    apiVersion: Optional[str] = None
    kind: Optional[str] = None
    labels: Optional[Dict[str, str]] = None
    stateful_set_spec: StatefulSetSpecConfig = StatefulSetSpecConfig()
    pod_management_policy: Optional[Literal["Parallel", "OrderedReady"]] = None
