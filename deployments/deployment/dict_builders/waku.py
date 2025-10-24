import re
from collections import defaultdict
from copy import deepcopy
from types import SimpleNamespace
from typing import Dict, List, Literal, Optional, Self, Tuple, TypeVar

from flask.ctx import _sentinel
from pydantic import BaseModel

from kube_utils import dict_get, dict_set

# initContainers

# class EnrOrAddress():
#     repo : str
#     tag : str
#     num : PositiveInt
#     service_names = List[str]
#     type_ : Literal["enr", "address"]


# ----------------------


def getEnrOrAddress_initContainer_old(config, type_: Literal["enr", "address"]):
    # Settings and flags for each type
    settings = {
        "address": {
            "shortname": "addrs",
            "version": "v0.1.0",
            "image": "soutullostatus/getaddress",
            "flag": "--lightpushnode",
        },
        "enr": {
            "shortname": "enr",
            "version": "v0.5.0",
            "image": "soutullostatus/getenr",
            "flag": "--discv5-bootstrap-node",
        },
    }
    cfg = settings.get(type_)
    if cfg is None:
        raise ValueError(f"Unknown type: {type_}")

    # Subvalues key: getEnr or getAddress
    key = f"get{type_.capitalize()}"  # e.g. "getEnr"
    subvalues = getattr(config, key, SimpleNamespace())
    repo = getattr(subvalues, "repo", cfg["image"])
    tag = getattr(subvalues, "tag", cfg["version"])
    num = getattr(subvalues, "num", 3)
    service_name = getattr(subvalues, "serviceName", "")

    # Compose basic container spec
    container = {
        "name": f"grab{type_}",
        "image": f"{repo}:{tag}",
        "imagePullPolicy": "IfNotPresent",
        "volumeMounts": [
            {
                "name": f"{type_}-data",
                "mountPath": f"/etc/{cfg['shortname']}",
            }
        ],
        "command": [f"/app/get{type_}.sh"],
        "args": [str(num), service_name],
    }

    return container


# class WakuDefaults:


def readiness_probe_command_health():
    prefix = ["/bin/sh", "-c"]
    command_block = """if curl -s http://127.0.0.1:8008/health | grep -q 'OK'; then
  exit 0;  # success, healthy state
else
  exit 1;  # failure, unhealthy state
fi
"""
    return prefix + [command_block]


def readiness_probe_command_metrics():
    prefix = ["/bin/sh", "-c"]
    command_block = """curl_output=$(curl -s http://127.0.0.1:8008/metrics);
curl_status=$?;
if [ $curl_status -ne 0 ]; then
  echo "Curl failed with status $curl_status";
  exit 1;  # failure, unhealthy state
fi;
echo "$curl_output" | awk '
  !/^#/ && /^libp2p_gossipsub_healthy_peers_topics / {
    print "Found gossipsub:", $0;
    if ($2 == 1.0) {
      exit 0;  # success, healthy state
    } else {
      exit 1;  # failure, unhealthy state
    }
  }
  END { if (NR == 0) exit 1 }  # If no matching line is found, exit with failure
'
"""
    return prefix + [command_block]


def value_or_preset(value, preset):
    pass


def bootstrap_readiness_probe():
    return {
        "failureThreshold": 1,
        "httpGet": {
            "path": "/health",
            "port": 8008,
        },
        "initialDelaySeconds": 1,
        "periodSeconds": 3,
        "successThreshold": 3,
        "timeoutSeconds": 5,
    }


def waku_readiness_probe(config: SimpleNamespace) -> dict:
    if "bootstrap" in config.name:
        return bootstrap_readiness_probe()
    elif "nodes" in config.name or getattr(config, "readinessProbe", None):
        return {
            "exec": {"command": waku_readiness_probe_command(config)},
            "successThreshold": 5,
            "initialDelaySeconds": 5,
            "periodSeconds": 1,
            "failureThreshold": 2,
            "timeoutSeconds": 5,
        }


def waku_readiness_probe_command(config: SimpleNamespace):
    try:
        return config.readinessProbe.command
    except AttributeError:
        pass

    print(config)
    if config.readinessProbe.type == "health":
        return readiness_probe_command_health()
    elif config.readinessProbe.type == "metrics":
        return readiness_probe_command_metrics()
    else:
        raise NotImplementedError()


# def args_to_list(args: dict):
#     args_list = []
#     for key, value in args.items():
#         if isinstance(value, list):
#             for sub_value in value:
#                 args_list.append(f"  {key}={sub_value}")
#         else:
#             args_list.append(f"  {key}={value}")


class Command(BaseModel):
    command: str
    args: List[str | Tuple[str, str]] = []
    multiline: bool = False

    # def add_args(self, args, *, on_duplicate="error"):
    #     if isinstance(args, dict):
    #         args = list(args.items())

    def add_arg(
        self,
        arg: str | Tuple[str, str],
        *,
        on_duplicate: Literal["error", "ignore", "replace"] = "error",
    ):
        """Add args to command.

        `on_duplicate` determines the behavior when an argument with the same key already exists.
        error: raises ValueError
        ignore: does not add the argument
        replace: replaces all instances of the argument in self.args with the single new argument passed in
        """
        self.add_args([arg], on_duplicate=on_duplicate)

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

            elif on_duplicate == "ignore":
                try:
                    flag, _value = arg
                except ValueError:
                    flag = arg
                if flag not in existing_args_map:
                    self.args.append(arg)

            elif on_duplicate == "replace":
                try:
                    flag, _value = arg
                except TypeError:
                    flag = arg
                if flag in existing_args_map:
                    self.args = [item for item in self.args if item != arg]
                    # Remove from map so it won't be replaced again.
                    del existing_args_map[flag]
                    self.args.insert(existing_args_map[flag], arg)
                else:
                    self.args.append(arg)

    # def add_args(self, args : List[str|Tuple[str, str]]|Dict[str, str],*,on_duplicate:Literal["error", "ignore", "replace"]="error"):
    #     if isinstance(args, dict):
    #         args = [(key, value) for key,value in args.items()]
    #     for arg in args:
    #         try:
    #             flag, value = arg
    #             self.args.append((flag, value))
    #         except TypeError:
    #             self.args.append(arg)

    def __str__(self) -> str:
        args = []
        for arg in self.args:
            if isinstance(arg, str):
                args.append(arg)
            else:
                args.append(f"{arg[0]}={arg[1]}")

        if not args:
            return self.command

        if self.multiline:
            args = [f"  {_arg}" for _arg in args]
            return f"{self.command} \\\n" + " \\\n".join(args)
        else:
            return f"{self.command} " + " ".join(args)


T = TypeVar("T")


class CommandConfig(BaseModel):
    commands: List[Command] = []

    def with_command(
        self,
        command: str,
        args: None | List[str | Tuple[str, Optional[str]]],
        *,
        multiline: bool = False,
    ):
        if args is None:
            args = []
        self.commands.append(Command(command=command, args=args, multiline=multiline))

    def with_source(self, file_path: str):
        raise NotImplementedError()

    _sentinel = object()

    def find_command(self, command_name: str, *, default: T | object = _sentinel) -> Command | T:
        # TODO: use this
        # TODO: make this use next(...) logic from presets.py
        for command in self.commands:
            if command.command == command_name:
                return command
        if default is _sentinel:
            raise ValueError(
                f"Command not found. command_name: `{command_name}` CommandConfig: `{self}`"
            )
        return default


def build_command(config: CommandConfig) -> List[str] | None:
    if not config.commands:
        return None
    print(f"asdf: {config}")
    command_lines = []
    for command in config.commands:
        command_lines.append(str(command))
    return build_container_command(command_lines)


class ContainerCommandBuilder(BaseModel):
    config: CommandConfig = CommandConfig()

    def build(self) -> List[str]:
        return build_command(self.config)

    def add_line(
        self,
        command: str,
        args: None | List[str | Tuple[str, Optional[str]]],
        *,
        multiline: bool = False,
    ) -> Self:
        if args is None:
            args = []
        self.config.commands.append(Command(command=command, args=args, multiline=multiline))
        return self


#     def with_source(self, num, source_file: str, var_name: str):
#         # TODO [config layout]: Allow specifying which env to source.
#         self.config.setup_commands.append(f". {source_file}")
#         enr = [f"${var_name}{i}" for i in range(1, num + 1)]
#         self.config.setup_commands.append("echo {var_name}s are {}".format(" ".join(enr)))

#     def with_enr(self, num) -> Self:
#         return self.with_source(num, "/etc/enr/enr.env", "ENR")

#     def with_addr(self, num) -> Self:
#         return self.with_source(num, "/etc/addrs/addrs.env", "addrs")

#     def with_nice(self, value: int):
#         self.config.setup_commands.append(f"nice -n {value} \\")

#     def with_args(
#         self, args: List[str | Tuple[str, str]], *, ignore_duplicates: bool = True
#     ) -> Self:
#         if not ignore_duplicates:
#             self.config.args.extend(args)
#         else:
#             for arg in args:
#                 if arg not in self.args:
#                     self.config.args.append(arg)
#         return self


def build_container_command(
    command_lines: List[str], prefix: Optional[List[str]] = None
) -> List[str]:
    if prefix is None:
        prefix = ["sh", "-c"]
    # The newline is added to the end of command to prevent chomp in dumped yaml.
    # We want `|` not `|-` in the final output.
    return prefix + ["\n".join(command_lines) + "\n"]


# TODO: Make conform to config/build pattern
# class ContainerCommandBuilder:
#     prefix: List[str]
#     command_lines: List[str]

#     def __init__(self):
#         self.prefix = ["sh", "-c"]
#         self.command_lines = []

#     def build(self):
#         # The newline is added to the end of command to prevent chomp in dumped yaml.
#         # We want `|` not `|-` in the final output.
#         return self.prefix + ["\n".join(self.command_lines) + "\n"]

#     def add_line(
#         self, command: str, args: List[str | Tuple[str, Optional[str]]], *, multiline: bool = False
#     ) -> Self:
#         _args = []
#         for flag, flag_args in args:
#             if flag_args is not None:
#                 _args.append(f"{flag}={flag_args}")
#             else:
#                 _args.append(flag)

#         if multiline:
#             _args = [f"  {_arg}" for _arg in _args]
#             self.command_lines.append(f"{command} \\\n" + " \\\n".join(_args))
#         else:
#             self.command_lines.append(f"{command} " + " ".join(_args))

#         return self


def waku_container_command(config) -> List[str]:
    prefix = ["sh", "-c"]
    command_lines = []

    # TODO [config layout]: Don't use includes in config.
    if "getEnr" in getattr(config, "includes", []):
        # TODO [config layout]: Allow specifying which env to source.
        command_lines.append(". /etc/enr/enr.env")
        num_enr = getattr(config.getEnr, "num", 3)
        enr = [f"$ENR{i}" for i in range(1, num_enr + 1)]
        command_lines.append("echo ENRs are {}".format(" ".join(enr)))

    print(f"asdf command: {config}")
    if "getAddress" in getattr(config, "includes", []):
        print("getAddress in includes for command")
        command_lines.append(". /etc/addrs/addrs.env")
        num_addrs = getattr(config.getAddress, "num", 3)
        addrs = [f"$addrs{i}" for i in range(1, num_addrs + 1)]
        command_lines.append("echo addrs are {}".format(" ".join(addrs)))

    try:
        nice = getattr(config.command, "nice")
        command_lines.append(f"nice -n {nice} \\")
    except AttributeError:
        pass

    args = args_to_list(waku_command_args(config))
    if config.type == "nodes" or config.type == "bootstrap":
        command_lines.append("/usr/bin/wakunode \\\n" + " \\\n".join(args))
    if config.type == "publisher":
        command_lines.append("python /app/traffic.py \\\n" + " \\\n".join(args))

    # The newline is added to the end of command to prevent chomp in dumped yaml.
    # We want `|` not `|-` in the final output.
    return prefix + ["\n".join(command_lines) + "\n"]


# TODO: PodSpec is in deployment["spec"]["template"]["spec"] for StatefulSet
# TODO: PodSpec is in deployment["spec"] for Pod
# TODO wip
# def add_container_dict(deployment, container):
#     kind = deployment["kind"]
#     if kind == "StatefulSet":
#         deployment["spec"]["template"]["spec"]["containers"].append()
#     if kind == "Pod":
#         deployment["spec"]["containers"].append()
# def add_container(deployment : V1StatefulSet | V1PodTemplateSpec | V1PodSpec | dict, container):


def command(command, args) -> str:
    prefix = ["sh", "-c"]
    command_lines = []
    args = args_to_list(args)
    command_lines.append(f"{command} \\\n" + " \\\n".join(args))

    # The newline is added to the end of command to prevent chomp in dumped yaml.
    # We want `|` not `|-` in the final output.
    return prefix + ["\n".join(command_lines) + "\n"]


def args_to_list(args: dict):
    args_list = []
    for key, value in args.items():
        if isinstance(value, list):
            for sub_value in value:
                args_list.append(f"  {key}={sub_value}")
        else:
            args_list.append(f"  {key}={value}")

    return args_list


def validate_nodes(deployment):
    # Ensure "len(--discv5-bootstrap-node)": matches ENRs
    raise NotImplementedError()


def waku_command_args(config) -> dict:
    presets_waku_nodes_command_regression = {
        "--relay": True,
        "--max-connections": 150,
        "--rest": True,
        "--rest-admin": True,
        "--rest-address": "0.0.0.0",
        "--discv5-discovery": True,
        "--discv5-enr-auto-update": True,
        "--log-level": "INFO",
        "--metrics-server": True,
        "--metrics-server-address": "0.0.0.0",
        "--discv5-bootstrap-node": ["$ENR1", "$ENR2", "$ENR3"],
        "--nat": "extip:${IP}",
        "--cluster-id": 2,
        "--shard": 0,
    }
    presets_waku_nodes_command_bootstrap_regression = {
        "--relay": False,
        "--rest": True,
        "--rest-address": "0.0.0.0",
        "--max-connections": 1000,
        "--discv5-discovery": True,
        "--discv5-enr-auto-update": True,
        "--log-level": "INFO",
        "--metrics-server": True,
        "--metrics-server-address": "0.0.0.0",
        "--nat": "extip:$IP",
        "--cluster-id": 2,
    }
    presets_waku_publisher_command_regression = {
        "--pubsub-topic": "/waku/2/rs/2/",
        "--protocols": "relay",
    }
    presets_waku_lightpush_client_nodes = {
        "--cluster-id": "2",
        "--log-level": "INFO",
        "--metrics-server-address": "0.0.0.0",
        "--metrics-server": "true",
        "--nat": "extip:${IP}",
        "--relay": "true",
        "--rest-address": "0.0.0.0",
        "--rest-admin": "true",
        "--rest": "true",
        "--shard": "0",
    }
    presets_waku_lightpush_server_nodes = {
        "--cluster-id": "2",
        "--discv5-bootstrap-node": ["$ENR1", "$ENR2", "$ENR3"],
        "--discv5-discovery": "true",
        "--discv5-enr-auto-update": "true",
        "--lightpush": "true",
        "--log-level": "INFO",
        "--max-connections": "500",
        "--metrics-server-address": "0.0.0.0",
        "--metrics-server": "true",
        "--nat": "extip:${IP}",
        "--relay": "true",
        "--rest-address": "0.0.0.0",
        "--rest-admin": "true",
        "--rest": "true",
        "--shard": "0",
    }

    # TODO move lightpush here

    def merge_presets(base_args: dict, preset_args: dict):
        result = {}
        for key in preset_args.keys() | base_args.keys():
            result[key] = base_args[key] if key in base_args else preset_args[key]
            # print(f"key: {key} new_value: {result[key]}")
        return result

    # args = config.command.args
    # print(f"args before: {args}")
    args = vars(config.command.args)
    # print(f"args after: {args}")
    presets = None
    if config.type == "publisher":
        print("asdfasdfdasf publisher")
        presets = presets_waku_publisher_command_regression
    if config.type == "nodes" or config.type == "bootstrap":
        if config.command.type == "lightpushClient":
            presets = presets_waku_lightpush_client_nodes
        if config.command.type == "lightpushServer":
            presets = presets_waku_lightpush_server_nodes
        if config.command.type == "regression":
            print("asdfasdfdasf regressionregressionregression")
            presets = presets_waku_nodes_command_regression
        if config.command.type == "bootstrap":
            print("asdfasdfdasf bootstrapbootstrapbootstrap")
            presets = presets_waku_nodes_command_bootstrap_regression
    if config.command.type == "blank":
        presets = {}
    if presets:
        print(f"preset: {presets_waku_nodes_command_regression}")
        args = merge_presets(vars(config.command.args), presets)

    print(f"waku_command_args args: {args}")

    return args


def camel_to_kebab(string):
    # Inserts a dash before capital letters, lowercases, and replaces underscores with dashes.
    return re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", string).replace("_", "-").lower()


def to_arg(string, to_kebab: bool):
    # if string not in ["contentTopics", "contentTopics"]:
    if to_kebab:
        arg = camel_to_kebab(string)
    else:
        arg = string
    if arg.startswith("--"):
        return arg
    else:
        return f"--{arg}"


def dict_to_arg(d, to_kebab):
    return {to_arg(k, to_kebab): v for k, v in d.items()}


def dict_to_kebab_case(d):
    return {camel_to_kebab(k): v for k, v in d.items()}


def waku_defaults() -> dict:
    global_defaults = {"namespace": "zerotesting"}
    waku_defaults = {"waku": {"command": {"args": {}}, "container": {}}}
    waku_nodes_defaults = {
        "name": "nodes-0",
        "namespace": "zerotesting",
        "serviceName": "zerotesting-service",
        "app": "zerotenkay",
        "numNodes": 10,
        "getEnr": {
            "repo": "soutullostatus/getenr",
            "tag": "v0.5.0",
            "num": 3,
            "serviceName": "zerotesting-bootstrap.zerotesting",
        },
        "command": {
            "type": "regression",
            "nice": 19,
            "args": {
                "--max-connections": 150,
            },
        },
        "readinessProbe": {
            "type": "metrics",
        },
        # "includes": {
        #     "getEnr": True,
        # },
        "includes": ["getEnr"],
        "image": {
            "repository": "soutullostatus/nwaku-jq-curl",
            "tag": "v0.34.0-rc1",
        },
        "dnsConfig": {
            "searches": [
                "zerotesting-service.zerotesting.svc.cluster.local",
            ],
        },
    }
    result = {}
    result.update(global_defaults)
    result.update(waku_defaults)
    result.update(waku_nodes_defaults)
    return result


def bootstrap_defaults() -> dict:
    global_defaults = {"namespace": "zerotesting"}
    waku_defaults = {"waku": {"command": {"args": {}}, "container": {}}}
    waku_values = {
        "dnsConfig": {
            "searches": [
                "zerotesting-service.zerotesting.svc.cluster.local",
                "zerotesting-bootstrap.zerotesting.svc.cluster.local",
            ]
        }
    }
    waku_bootstrap_defaults = {
        "name": "bootstrap",
        "namespace": "zerotesting",
        "serviceName": "zerotesting-bootstrap",
        "app": "zerotenkay-bootstrap",
        "numNodes": 3,
        # "getEnr": {
        #     "repo": "soutullostatus/getenr",
        #     "tag": "v0.5.0",
        #     "num": 3,
        #     "serviceName": "zerotesting-bootstrap.zerotesting",
        # },
        "command": {
            "type": "bootstrap",
            #     "nice": 19,
            #     "args": {
            #         "--max-connections": 150,
            # },
        },
        "readinessProbe": {
            "type": "health",
        },
        # "includes": {
        #     "getEnr": True,
        # },
        # "includes": [
        #     "getEnr"
        # ],
        "image": {
            "repository": "soutullostatus/nwaku-jq-curl",
            "tag": "v0.34.0-rc1",
        },
    }
    result = {}
    result.update(global_defaults)
    result.update(waku_defaults)
    result.update(waku_bootstrap_defaults)
    result.update(waku_values)
    return result


def defaults_lightpush():
    command_args = {
        "--lightpushnode": "$addrs1",
        "--relay": False,
        "--rest": True,
        "--rest-admin": True,
        "--rest-address": "0.0.0.0",
        "--log-level": "INFO",
        "--metrics-server": True,
        "--metrics-server-address": "0.0.0.0",
        "--nat": "extip:${IP}",
        "--cluster-id": 2,
        "--shard": 0,
    }
    lightpush_defaults = {"waku": {"command": {"args": command_args}, "container": {}}}
    result = {}
    result.update(lightpush_defaults)
    return result


def preprocess_values(config: dict) -> SimpleNamespace:
    adjusted_values = deepcopy(config)

    # TODO [remove --values]: When cli_values are removed, we won't need any merging schemes.
    def shift_dict(key: str):
        subdict = dict_get(config, key, default=None, sep=".")
        if subdict:
            adjusted_values.update(subdict)

    kebab_args = True
    # import pdb; pdb.set_trace()
    if adjusted_values.get("name", "") == "nodes":
        adjusted_values.update(waku_defaults())
        if dict_get(adjusted_values, "waku.nodes.command.type", sep=".", default=None):
            adjusted_values.update(defaults_lightpush())
        shift_dict("waku.nodes")
    if adjusted_values.get("name", "") == "bootstrap":
        # print("it's a bootstrap!")
        adjusted_values.update(bootstrap_defaults())
        # print(f"1 adjusted_values: {adjusted_values}")
        shift_dict("waku.bootstrap")
        # dict_set(adjusted_values, "waku.bootstrap.command.type", "bootstrap", sep=".", replace_leaf=True)
        dict_set(adjusted_values, "command.type", "bootstrap", sep=".", replace_leaf=True)
        # print(f"2 adjusted_values: {adjusted_values}")
    if adjusted_values.get("name", "") == "publisher":
        shift_dict("waku.publisher")
    if adjusted_values.get("name", "") == "get_store_messages":
        kebab_args = False
        # dict_set(adjusted_values, "command.type", "bootstrap", sep=".", replace_leaf=True)
        key = "waku.getStoreMessages.command.args"
        args_dict = dict_get(adjusted_values, key, sep=".")
        dict_set(
            adjusted_values, key, dict_to_arg(args_dict, kebab_args), sep=".", replace_leaf=True
        )

        ds_config = {
            "dnsConfig": {
                "searches": [
                    "zerotesting-store.zerotesting.svc.cluster.local",
                ]
            }
        }
        adjusted_values.update(ds_config)

    if adjusted_values.get("name", "") == "get_filter_messages":
        kebab_args = False

        key = "waku.getFilterMessages.command.args"
        args_dict = dict_get(adjusted_values, key, sep=".")
        dict_set(
            adjusted_values, key, dict_to_arg(args_dict, kebab_args), sep=".", replace_leaf=True
        )

        ds_config = {
            "dnsConfig": {
                "searches": [
                    "zerotesting-filter.zerotesting.svc.cluster.local",
                ]
            }
        }
        adjusted_values.update(ds_config)

        container_image = dict_get(
            config, "image.repository", sep=".", default="soutullostatus/get_filter_messages"
        )
        container_tag = dict_get(config, "image.tag", sep=".", default="v0.2.0")
        adjusted_values["image"] = {
            "repository": container_image,
            "tag": container_tag,
        }

    if adjusted_values.get("name", "") == "nodes_relay-lightpush":
        shift_dict("waku.nodes")

    includes = []
    try:
        if adjusted_values.get("includes", {}).get("getEnr", None):
            includes.append("getEnr")
        if adjusted_values.get("includes", {}).get("getAddress", None):
            includes.append("getAddress")
    except AttributeError:
        pass
    adjusted_values["includes"] = includes

    if not adjusted_values.get("command", None):
        adjusted_values["command"] = {}
    if not adjusted_values.get("command", {}).get("args", None):
        adjusted_values["command"]["args"] = {}
        # print(f"asdf adjusted_values: {adjusted_values['command']['args']}")

    adjusted_values["command"]["args"] = dict_to_arg(adjusted_values["command"]["args"], kebab_args)

    import json

    print(f"adjusted_values: ```{json.dumps(adjusted_values)}```")

    return dict_to_namespace(adjusted_values)


def dict_to_namespace(d: dict):
    if isinstance(d, dict):
        return SimpleNamespace(**{key: dict_to_namespace(value) for key, value in d.items()})
    return d


def node_resources(config: SimpleNamespace):
    if "nodes" in config.name or getattr(config, "type", None) == "nodes":
        return {
            "requests": {
                "memory": "64Mi",
                "cpu": "150m",
            },
            "limits": {
                "memory": "600Mi",
                "cpu": "400m",
            },
        }

    if "bootstrap" in config.name or getattr(config, "type", None) == "bootstrap":
        return {
            "requests": {
                "memory": "64Mi",
                "cpu": "50m",
            },
            "limits": {
                "memory": "768Mi",
                "cpu": "400m",
            },
        }


def waku_container(config) -> dict:
    container = {
        "name": "waku",
        "image": f'{getattr(getattr(config, "image", {}), "repository", "soutullostatus/nwaku-jq-curl")}:{getattr(getattr(config, "image", {}), "tag", "v0.34.0-rc1")}',
        "imagePullPolicy": "IfNotPresent",
        "ports": [
            {"containerPort": 8645},
            {"containerPort": 8008},
        ],
        "readinessProbe": waku_readiness_probe(config),
        "resources": node_resources(config),
        "env": (
            [
                {
                    "name": "IP",
                    "valueFrom": {
                        "fieldRef": {
                            "fieldPath": "status.podIP",
                        }
                    },
                }
            ]
            + (
                [
                    {
                        "name": "POSTGRES_URL",
                        "value": "postgres://wakuuser:wakupassword@127.0.0.1:5432/wakumessages",
                    }
                ]
                if getattr(config, "storeNode", False)
                else []
            )
        ),
        "command": waku_container_command(config),
    }

    # Add volume mounts (if applicable)
    def add_volume_mount(vol: dict):
        if getattr(container, "volumeMounts", None) is None:
            container["volumeMounts"] = []
        container["volumeMounts"].append(vol)

    custom_mounts = getattr(config, "volumesMounts", [])
    if custom_mounts:
        add_volume_mount(custom_mounts)

    if "getAddress" in getattr(config, "includes", []):
        get_address = {"name": "address-data", "mountPath": "/etc/addrs"}
        add_volume_mount(get_address)

    if "getEnr" in getattr(config, "includes", []):
        get_enr = {"name": "enr-data", "mountPath": "/etc/enr"}
        add_volume_mount(get_enr)

    return container


def volumes(config: SimpleNamespace):
    result = []
    if getattr(config, "volumes", []):
        volumes.append(config.volumes)

    if "getEnr" in getattr(config, "includes", []):
        result.append({"name": "enr-data", "emptyDir": {}})

    if "getAddress" in getattr(config, "includes", []):
        result.append({"name": "address-data", "emptyDir": {}})

    if getattr(config, "storeNode", False):
        result.append({"name": "postgres-data", "emptyDir": {}})

    return result


def waku_init_containers(config: SimpleNamespace):

    init_containers = []

    custom_init_containers = getattr(config, "initContainers", [])
    if custom_init_containers:
        init_containers.extend(custom_init_containers)

    if "getEnr" in config.includes:
        init_containers.append(getEnrOrAddress_initContainer_old(config, "enr"))

    if "getAddress" in config.includes:
        init_containers.append(getEnrOrAddress_initContainer_old(config, "address"))

    return init_containers


def postgress_container() -> dict:
    prefix = ["sh", "-c"]
    command = prefix + ["\n".join(["pg_isready -U wakuuser -d wakumessages"]) + "\n"]
    return {
        "name": "postgres",
        "image": "postgres:15.1-alpine",
        "imagePullPolicy": "IfNotPresent",
        "volumeMounts": [
            {
                "name": "postgres-data",
                "mountPath": "/var/lib/postgresql/data",
            }
        ],
        "env": [
            {
                "name": "POSTGRES_DB",
                "value": "wakumessages",
            },
            {"name": "POSTGRES_USER", "value": "wakuuser"},
            {
                "name": "POSTGRES_PASSWORD",
                "value": "wakupassword",
            },
        ],
        "ports": [{"containerPort": 5432}],
        "readinessProbe": {
            "exec": {"command": command},
            "initialDelaySeconds": 5,
            "periodSeconds": 2,
            "timeoutSeconds": 5,
        },
    }


def waku_get_filter_messages(config_dict: SimpleNamespace):
    config = preprocess_values(config_dict)

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": "get-filter-messages",
            "namespace": config_dict.get("namespace", "zerotesting"),
        },
        "spec": {
            "restartPolicy": "Never",
            **(
                {"dnsConfig": vars(config.dnsConfig)}
                if hasattr(config, "dnsConfig") and config.dnsConfig
                else {}
            ),
            "containers": [
                {
                    "name": "container",
                    "image": f"{config.image.repository}:{config.image.tag}",
                    "imagePullPolicy": "Always",
                    "command": command(
                        "python /app/filter_msg_retriever.py",
                        vars(config.waku.getFilterMessages.command.args),
                    ),
                }
            ],
        },
    }


def waku_get_store_messages(config_dict: SimpleNamespace):
    config = preprocess_values(config_dict)

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "get-store-messages", "namespace": "zerotesting"},
        "spec": {
            "restartPolicy": "Never",
            **(
                {"dnsConfig": vars(config.dnsConfig)}
                if hasattr(config, "dnsConfig") and config.dnsConfig
                else {}
            ),
            "containers": [
                {
                    "name": "container",
                    "image": "soutullostatus/get_store_messages:v0.1.11",
                    "imagePullPolicy": "Always",
                    "command": command(
                        "python /app/store_msg_retriever.py",
                        vars(config.waku.getStoreMessages.command.args),
                    ),
                }
            ],
        },
    }
