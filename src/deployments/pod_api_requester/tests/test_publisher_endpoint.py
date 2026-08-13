import pytest

from src.deployments.pod_api_requester import pod_api_requester as par
from src.deployments.pod_api_requester.pod_api_requester import publisher_endpoint


def _discover():
    return par._get_api_requester_info(namespace="ns", service_name="svc", app="app")


def test_the_override_replaces_nodeport_discovery(mocker):
    """The k8s lookup must not run at all, since its answer is the unreachable path."""
    api = mocker.patch.object(par.client, "CoreV1Api")
    with publisher_endpoint("127.0.0.1", 54321):
        assert _discover() == ("127.0.0.1", "54321")
    api.assert_not_called()


def test_discovery_is_restored_afterwards(mocker):
    mocker.patch.object(par, "_get_api_requester_info", wraps=par._get_api_requester_info)
    with publisher_endpoint("127.0.0.1", 1):
        pass
    assert par._endpoint_override is None


def test_nesting_restores_the_outer_override():
    with publisher_endpoint("127.0.0.1", 1):
        with publisher_endpoint("127.0.0.1", 2):
            assert _discover() == ("127.0.0.1", "2")
        assert _discover() == ("127.0.0.1", "1")


def test_an_exception_still_restores_discovery():
    with pytest.raises(ValueError):
        with publisher_endpoint("127.0.0.1", 1):
            raise ValueError("boom")
    assert par._endpoint_override is None


def test_the_url_the_requester_builds_points_at_the_tunnel():
    template = "http://{target_ip}:{node_port}/process"
    with publisher_endpoint("127.0.0.1", 54321):
        ip, port = _discover()
    assert template.format(target_ip=ip, node_port=port) == "http://127.0.0.1:54321/process"
