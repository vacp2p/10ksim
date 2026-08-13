import asyncio

import pytest

from src.deployments.core import port_forward as pf


class FakeStdout:
    def __init__(self, lines):
        self._lines = list(lines)

    async def readline(self):
        return self._lines.pop(0) if self._lines else b""


class FakeProc:
    def __init__(self, lines, returncode=None):
        self.stdout = FakeStdout(lines)
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


def _spawn(proc, captured=None):
    async def create(*cmd, **kwargs):
        if captured is not None:
            captured.extend(cmd)
        return proc

    return create


@pytest.mark.asyncio
async def test_reads_back_the_port_kubectl_chose(mocker):
    """The local port is left to the kernel, so it has to be parsed rather than assumed."""
    proc = FakeProc([b"Forwarding from 127.0.0.1:54321 -> 8645\n"])
    mocker.patch.object(asyncio, "create_subprocess_exec", _spawn(proc))

    async with pf.port_forward("svc/zerotesting-publisher", 8645, "zerotesting") as (host, port):
        assert (host, port) == ("127.0.0.1", 54321)


@pytest.mark.asyncio
async def test_skips_noise_before_the_forwarding_line(mocker):
    proc = FakeProc([b"some warning\n", b"Forwarding from 127.0.0.1:7000 -> 8645\n"])
    mocker.patch.object(asyncio, "create_subprocess_exec", _spawn(proc))

    async with pf.port_forward("svc/x", 8645, "ns") as (_, port):
        assert port == 7000


@pytest.mark.asyncio
async def test_the_tunnel_is_closed_on_the_way_out(mocker):
    proc = FakeProc([b"Forwarding from 127.0.0.1:7000 -> 8645\n"])
    mocker.patch.object(asyncio, "create_subprocess_exec", _spawn(proc))

    async with pf.port_forward("svc/x", 8645, "ns"):
        pass
    assert proc.terminated, "kubectl must not be left running after the run"


@pytest.mark.asyncio
async def test_a_tunnel_that_never_listens_fails_loudly(mocker):
    """Silence here would look like a publisher that is simply not answering."""
    proc = FakeProc([])  # kubectl exited without ever forwarding
    mocker.patch.object(asyncio, "create_subprocess_exec", _spawn(proc))

    with pytest.raises(RuntimeError, match="exited before it was listening"):
        async with pf.port_forward("svc/x", 8645, "ns"):
            pass


@pytest.mark.asyncio
async def test_the_namespace_and_target_reach_kubectl(mocker):
    proc = FakeProc([b"Forwarding from 127.0.0.1:7000 -> 8645\n"])
    cmd = []
    mocker.patch.object(asyncio, "create_subprocess_exec", _spawn(proc, cmd))

    async with pf.port_forward("svc/zerotesting-publisher", 8645, "zerotesting"):
        pass

    assert "port-forward" in cmd
    assert "svc/zerotesting-publisher" in cmd
    assert ":8645" in cmd
    assert cmd[cmd.index("-n") + 1] == "zerotesting"
