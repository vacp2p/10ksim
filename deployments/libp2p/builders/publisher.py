from dataclasses import dataclass
from typing import List, Literal, Optional

from core.configs.container import Image

@dataclass
class PublisherConfig:
    """
    Publisher configuration for http message injector.    
    All parameters are Optional. Only explicitly set values will be passed
    """
    pubsub_topic: Optional[str] = None
    msg_size_bytes: Optional[int] = None
    delay_seconds: Optional[int] = None
    messages: Optional[int] = None
    peer_selection: Optional[Literal["service", "id"]] = None
    port: Optional[int] = None
    network_size: Optional[int] = None
    
    def to_args(self) -> List[str]:

        args = []
        
        if self.pubsub_topic is not None:
            args.append(f"--pubsub-topic={self.pubsub_topic}")
        if self.msg_size_bytes is not None:
            args.append(f"--msg-size-bytes={self.msg_size_bytes}")
        if self.delay_seconds is not None:
            args.append(f"--delay-seconds={self.delay_seconds}")
        if self.messages is not None:
            args.append(f"--messages={self.messages}")
        if self.peer_selection is not None:
            args.append(f"--peer-selection={self.peer_selection}")
        if self.port is not None:
            args.append(f"--port={self.port}")
        if self.network_size is not None:
            args.append(f"--network-size={self.network_size}")
        
        return args


class Publisher:

    DEFAULT_IMAGE = Image(repo="ufarooqstatus/libp2p-publisher", tag="v1.0")
    DEFAULT_NAMESPACE = "refactortesting-libp2p"
    DEFAULT_SERVICE_NAME = "nimp2p-service"

    @staticmethod
    def create_pod_spec(
        config: Optional[PublisherConfig] = None,
        namespace: Optional[str] = None,
        service_name: Optional[str] = None,
        image: Optional[Image] = None,
    ) -> dict:

        #Create publisher pod specification
        if config is None:
            config = PublisherConfig()
        if namespace is None:
            namespace = Publisher.DEFAULT_NAMESPACE
        if service_name is None:
            service_name = Publisher.DEFAULT_SERVICE_NAME
        if image is None:
            image = Publisher.DEFAULT_IMAGE

        service_dns = f"{service_name}.{namespace}.svc.cluster.local"
        
        args = config.to_args()
        if args:
            args_str = " \\\n".join(["python /app/traffic.py"] + args)
        else:
            args_str = "python /app/traffic.py"

        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": "publisher",
                "namespace": namespace,
            },
            "spec": {
                "restartPolicy": "Never",
                "dnsConfig": {
                    "searches": [service_dns],
                },
                "containers": [
                    {
                        "name": "publisher-container",
                        "image": str(image),
                        "imagePullPolicy": "Always",
                        "command": ["sh", "-c"],
                        "args": [args_str + "\n"],
                    }
                ],
            },
        }


    @staticmethod
    def create_pod_spec_simple(
        messages: Optional[int] = None,
        msg_size_bytes: Optional[int] = None,
        delay_seconds: Optional[int] = None,
        peer_selection: Optional[Literal["service", "id"]] = None,
        network_size: Optional[int] = None,
        pubsub_topic: Optional[str] = None,
        port: Optional[int] = None,
        namespace: Optional[str] = None,
        service_name: Optional[str] = None,
    ) -> dict:

        # Create publisher pod with individual parameters.
        config = PublisherConfig(
            pubsub_topic=pubsub_topic,
            msg_size_bytes=msg_size_bytes,
            delay_seconds=delay_seconds,
            messages=messages,
            peer_selection=peer_selection,
            port=port,
            network_size=network_size,
        )
        return Publisher.create_pod_spec(
            config=config,
            namespace=namespace,
            service_name=service_name,
        )
