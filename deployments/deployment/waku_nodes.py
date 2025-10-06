from copy import deepcopy
from types import SimpleNamespace
from typing import List, Literal

from kube_utils import dict_get


def getEnrOrAddress_initContainer(config, type_: Literal["enr", "address"]):
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


def waku_readiness_probe_health() -> str:
    prefix = ["/bin/sh", "-c"]
    command_block = """if curl -s http://127.0.0.1:8008/health | grep -q 'OK'; then
    exit 0;  # success, healthy state
  else
    exit 1;  # failure, unhealthy state
  fi
"""
    return prefix + [command_block]


def waku_readiness_probe_metrics() -> str:
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


def waku_readiness_probe(config: SimpleNamespace):
    try:
        return config.readinessProbe.command
    except AttributeError:
        pass

    print(config)
    if config.readinessProbe.type == "health":
        return waku_readiness_probe_health()
    elif config.readinessProbe.type == "metrics":
        return waku_readiness_probe_metrics()
    else:
        raise NotImplementedError()


def waku_container_command(config) -> List[str]:
    prefix = ["sh", "-c"]
    command_lines = []

    # TODO [config layout]: Don't use includes in config.
    if "getEnr" in getattr(config, "includes", []):
        # TODO [config layout]: Allow specifying which env to source.
        command_lines.append(". /etc/enr/enr.env")
        num_enr = getattr(config.getEnr, "num", 3)
        enr = [f"$ENR{i}" for i in range(num_enr)]
        command_lines.append("echo ENRs are {}".format(" ".join(enr)))

    if "getAddress" in getattr(config, "includes", []):
        command_lines.append(". /etc/addrs/addrs.env")
        num_addrs = getattr(config.getAddress, "num", 3)
        addrs = [f"$addrs{i}" for i in range(num_addrs)]
        command_lines.append("echo addrs are {}".format(" ".join(addrs)))

    try:
        nice = getattr(config.command, "nice")
        command_lines.append(f"nice -n {nice} \\")
    except AttributeError:
        pass

    args = args_to_list(waku_command_args(config))
    command_lines.append("/usr/bin/wakunode \\\n" + " \\\n".join(args))

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

    def merge_presets(args: dict, preset_args):
        result = {}
        for key in preset_args.keys() | args.keys():
            result[key] = args[key] if key in args else preset_args[key]
        return result

    args = config.command.args
    if config.command.type == "regression":
        args = merge_presets(vars(config.command.args), presets_waku_nodes_command_regression)

    return args


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


def preprocess_values(config: dict) -> SimpleNamespace:
    """Build config by merging defaults with config."""
    adjusted_values = deepcopy(config)
    adjusted_values.update(waku_defaults())

    # TODO [remove --values]: When cli_values are removed, we won't need any merging schemes.
    def shift_dict(key: str):
        subdict = dict_get(config, key, default=None, sep=".")
        if subdict:
            adjusted_values.update(subdict)

    # Move waku.<service>.settings to .settings.
    shift_dict("waku.bootstrap")
    shift_dict("waku.publisher")
    shift_dict("waku.nodes")
    includes = []
    if adjusted_values.get("includes", {}).get("getEnr", None):
        includes.append("getEnr")
    if adjusted_values.get("includes", {}).get("getAddress", None):
        includes.append("getAddress")
    adjusted_values["includes"] = includes

    if not adjusted_values.get("command", None):
        adjusted_values["command"] = {}
    if not adjusted_values.get("command", {}).get("args", None):
        adjusted_values["command"]["args"] = {}

    return dict_to_namespace(adjusted_values)


def dict_to_namespace(d: dict):
    if isinstance(d, dict):
        return SimpleNamespace(**{key: dict_to_namespace(value) for key, value in d.items()})
    return d


def waku_node(config_dict: dict):
    config = preprocess_values(config_dict)
    return {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {"name": config.name, "namespace": config.namespace},
        "spec": {
            "replicas": config.numNodes,
            "podManagementPolicy": "Parallel",
            "serviceName": config.serviceName,
            "selector": {
                "matchLabels": {
                    "app": config.app,
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": config.app,
                    },
                },
                "spec": {
                    **(
                        {"dnsConfig": vars(config.dnsConfig)}
                        if hasattr(config, "dnsConfig") and config.dnsConfig
                        else {}
                    ),
                    "volumes": [
                        *getattr(config, "volumes", []),
                        *(
                            [{"name": "enr-data", "emptyDir": {}}]
                            if "getEnr" in getattr(config, "includes", [])
                            else []
                        ),
                        *(
                            [{"name": "address-data", "emptyDir": {}}]
                            if "getAddress" in getattr(config, "includes", [])
                            else []
                        ),
                        *(
                            [{"name": "postgres-data", "emptyDir": {}}]
                            if getattr(config, "storeNode", False)
                            else []
                        ),
                    ],
                    "initContainers": [
                        *getattr(config, "initContainers", []),
                        *(
                            [getEnrOrAddress_initContainer(config, "enr")]
                            if "getEnr" in config.includes
                            else []
                        ),
                        *(
                            [getEnrOrAddress_initContainer(config, "address")]
                            if "getaddress" in config.includes
                            else []
                        ),
                    ],
                    "containers": [
                        {
                            "name": "waku",
                            "image": f'{getattr(getattr(config, "image", {}), "repository", "soutullostatus/nwaku-jq-curl")}:{getattr(getattr(config, "image", {}), "tag", "v0.34.0-rc1")}',
                            "imagePullPolicy": "IfNotPresent",
                            "ports": [
                                {"containerPort": 8645},
                                {"containerPort": 8008},
                            ],
                            "volumeMounts": (
                                getattr(config, "volumesMounts", [])
                                + (
                                    [{"name": "address-data", "mountPath": "/etc/addrs"}]
                                    if "getAddress" in getattr(config, "includes", [])
                                    else []
                                )
                                + (
                                    [{"name": "enr-data", "mountPath": "/etc/enr"}]
                                    if "getEnr" in getattr(config, "includes", [])
                                    else []
                                )
                            ),
                            "readinessProbe": {
                                "exec": {"command": waku_readiness_probe(config)},
                                "successThreshold": 5,
                                "initialDelaySeconds": 5,
                                "periodSeconds": 1,
                                "failureThreshold": 2,
                                "timeoutSeconds": 5,
                            },
                            "resources": {
                                "requests": {
                                    "memory": "64Mi",
                                    "cpu": "150m",
                                },
                                "limits": {
                                    "memory": "600Mi",
                                    "cpu": "400m",
                                },
                            },
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
                    ],
                },
            },
        },
    }
