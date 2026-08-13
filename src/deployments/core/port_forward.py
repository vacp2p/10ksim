"""Reach an in-cluster service through the API server rather than its NodePort.

`kubectl port-forward` tunnels over the API server, so it works wherever kubectl does.
A NodePort needs the node reachable on a high port, which is a separate network path and
is not always open from where a run is driven.
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import AsyncIterator, Tuple

from src.deployments.core.k8s_kubeconfig import get_config_file

logger = logging.getLogger(__name__)

_FORWARDING = re.compile(r"Forwarding from 127\.0\.0\.1:(\d+)")


async def _local_port(proc: asyncio.subprocess.Process) -> int:
    """Read the port kubectl chose from its first Forwarding line."""
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            raise RuntimeError("kubectl port-forward exited before it was listening")
        line = raw.decode(errors="replace").strip()
        logger.debug(f"port-forward: {line}")
        found = _FORWARDING.search(line)
        if found:
            return int(found.group(1))


@asynccontextmanager
async def port_forward(
    target: str, remote_port: int, namespace: str, *, ready_timeout_s: int = 30
) -> AsyncIterator[Tuple[str, int]]:
    """Yield `(host, port)` for a tunnel to `target`, eg. `svc/zerotesting-publisher`.

    The local port is left for the kernel to choose and read back from kubectl, so
    parallel runs cannot collide on it.
    """
    cfg = get_config_file()
    cmd = (
        ["kubectl"]
        + (["--kubeconfig", cfg] if cfg else [])
        + ["-n", namespace, "port-forward", target, f":{remote_port}"]
    )
    logger.info(f"Opening a port-forward to {target}:{remote_port} in `{namespace}`")
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        port = await asyncio.wait_for(_local_port(proc), ready_timeout_s)
        logger.info(f"Port-forward listening on 127.0.0.1:{port} -> {target}:{remote_port}")
        yield "127.0.0.1", port
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        logger.info(f"Closed the port-forward to {target}")
