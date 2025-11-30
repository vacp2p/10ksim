import asyncio
import json
import logging
from pathlib import Path
from typing import Literal, Optional

import requests
from kubernetes import client, config
from pydantic import NonNegativeInt

import kube_utils

logger = logging.getLogger(__name__)


async def example():
    config.load_kube_config("/path_to_kube_config.yaml")
    config.load_kube_config()  # WARNING! LOCAL
    publish_message(
        namespace="zerotesting",
        message_type="lightpush",
        pod_name_template="lpclient-0-0",
        service="zerotesting-lightpush-client",
    )


def read_deployment_file(path: Path, namespace: str):
    raise NotImplementedError("TODO")
    # with open(Path(__file__).parent / path, "r") as deployment_yaml:
    #     import yaml
    #     deployment_spec = yaml.safe_load(deployment_yaml.read())
    #     deployment_spec["metadata"]["namespace"] = namespace
    #     return deployment_spec


async def launch_prerequisites(namespace: str):
    raise NotImplementedError("TODO")
    # TODO: publisher-service, role/bind, config.yaml


PublishType = Literal["lightpush", "relay"]


async def publish_message(
    namespace: str,
    message_type: PublishType,
    *,
    pod_name_template: Optional[str] = None,
    service: Optional[str] = None,
    stateful_set_name: Optional[str] = None,
    port: NonNegativeInt = 80,
):
    if message_type == "lightpush":
        endpoint = "lightpush-publish-static-sharding"
    elif message_type == "relay":
        raise NotImplementedError()
    else:
        raise ValueError("Unknown message type")

    data = {
        "target": {
            "name": "dummy",
            "service": service,
            "name_template": pod_name_template,
            "stateful_set": stateful_set_name,
            "port": port,
        },
        "endpoint": endpoint,
    }

    return await pod_api_request(
        namespace=namespace,
        service_name="zerotesting-publisher",
        app="zerotenkay-publisher",
        data=data,
    )


class PodApiRequestError(Exception):
    pass


async def pod_api_request(
    namespace: str,
    service_name: str,
    app: str,
    data: dict,
    *,
    publisher_pod: str | NonNegativeInt = 0,
) -> dict:
    v1 = client.CoreV1Api()

    try:
        pods = v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={app}")
        if isinstance(publisher_pod, str):
            pod = next(pod for pod in pods.items if pod.metadata.name == publisher_pod)
        else:
            pod = pods.items[publisher_pod]
    except IndexError as e:
        logger.error(f"No pod found. app: `{app}` pod_index: `{publisher_pod}`")
        raise ValueError() from e
    except StopIteration as e:
        logger.error(f"No pod found. app: `{app}` pod_name: `{publisher_pod}`")
        raise ValueError() from e

    # Get publisher IP.
    node = v1.read_node(name=pod.spec.node_name)
    target_ip = kube_utils.get_node_ip(node)

    # Get publisher port.
    service = v1.read_namespaced_service(service_name, namespace)
    node_port = service.spec.ports[0].node_port
    if node_port is None:
        raise ValueError(f"Failed to find port for service. Service: `{service.metadata.name}`")

    url = f"http://{target_ip}:{node_port}/process"

    logger.info(f"publishing message. url: `{url}` data: `{data}`")
    response = requests.post(url, json=data)
    response_obj = json.loads(response.text)
    if response.status_code != 200:
        err = response_obj["detail"].replace("\n", "\n")
        logger.error(err)
        raise PodApiRequestError(response_obj)

    try:
        # Assuming that the pod we made the API request to returns a response with a JSON object.
        inner_response_obj = json.loads(response_obj["response"]["text"])
        response_obj["inner_response"] = inner_response_obj
        if response_obj["response"]["status_code"] != 200:
            # JsWaku puts the error under the key "error".
            try:
                err = inner_response_obj["error"].replace("\n", "\n")
            except KeyError as e:
                err = "<Failed to extract inner error>"
            logger.error(f"Publisher request returned failure. inner_error: `{err}`")
            raise PodApiRequestError(response_obj)
    except json.JSONDecodeError as e:
        # Response was not a Json object.
        pass
    except KeyError as e:
        err = response_obj["exception"].replace("\n", "\n")
        logger.error(f"The publisher's API request attempt failed. Exception: `{err}`")
        raise PodApiRequestError(response_obj) from e

    logger.info(f"Response: `{response_obj}`")
    return response_obj


if __name__ == "__main__":
    asyncio.run(main())
