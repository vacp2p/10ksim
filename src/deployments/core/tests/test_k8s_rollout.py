from unittest.mock import AsyncMock, MagicMock

import pytest
from kubernetes.client.rest import ApiException

from src.deployments.core import k8s_rollout
from src.deployments.core.k8s_rollout import (
    check_pod_condition,
    poll_rollout_status,
    wait_for_rollout,
)


def _pod_with_conditions(conditions):
    # conditions: list of (type, status) tuples.
    pod = MagicMock()
    pod.status.conditions = [MagicMock(type=t, status=s) for t, s in conditions]
    return pod


def _statefulset(
    *, desired, ready, available=None, updated=None, current_rev="r1", update_rev="r1"
):
    obj = MagicMock()
    obj.kind = "StatefulSet"
    obj.spec.replicas = desired
    obj.status.ready_replicas = ready
    obj.status.available_replicas = desired if available is None else available
    obj.status.updated_replicas = desired if updated is None else updated
    obj.status.current_revision = current_rev
    obj.status.update_revision = update_rev
    return obj


# --------------------------------------------------------------------------- #
# check_pod_condition  (pure given a pod object)
# --------------------------------------------------------------------------- #
class TestCheckPodCondition:
    def test_ready_true_returns_true(self):
        pod = _pod_with_conditions([("Ready", "True")])
        assert check_pod_condition(pod) is True

    def test_ready_false_returns_false(self):
        pod = _pod_with_conditions([("Ready", "False")])
        assert check_pod_condition(pod) is False

    def test_no_conditions_returns_false(self):
        pod = MagicMock()
        pod.status.conditions = None
        assert check_pod_condition(pod) is False

    def test_custom_tuple_condition(self):
        pod = _pod_with_conditions([("Initialized", "True")])
        assert check_pod_condition(pod, ("Initialized", "True")) is True
        assert check_pod_condition(pod, ("Ready", "True")) is False

    def test_callable_condition_false_is_propagated(self):
        pod = MagicMock()
        condition = MagicMock(return_value=False)
        assert check_pod_condition(pod, condition) is False
        condition.assert_called_once_with(pod)


# --------------------------------------------------------------------------- #
# poll_rollout_status  (reads live object via get_namespaced)
# --------------------------------------------------------------------------- #
class TestPollRolloutStatus:
    def test_statefulset_uses_live_object(self, mocker):
        stale = _statefulset(desired=3, ready=0)
        live = _statefulset(desired=3, ready=3)
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=live)
        assert poll_rollout_status(stale) is True

    def test_statefulset_uses_live_object_not_stale_object(self, mocker):
        stale = _statefulset(desired=3, ready=3)
        live = _statefulset(desired=3, ready=1)
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=live)
        assert poll_rollout_status(stale) is False

    def test_statefulset_mid_revision_rollout_is_false(self, mocker):
        # Counts match but revisions differ => still rolling.
        obj = _statefulset(desired=3, ready=3, current_rev="r1", update_rev="r2")
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=obj)
        assert poll_rollout_status(obj) is False

    def test_pod_ready_is_true(self, mocker):
        pod = _pod_with_conditions([("Ready", "True")])
        pod.kind = "Pod"
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=pod)
        assert poll_rollout_status(pod) is True

    def test_service_is_immediately_ready(self, mocker):
        svc = MagicMock()
        svc.kind = "Service"
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=svc)
        assert poll_rollout_status(svc) is True

    def test_unsupported_kind_raises(self, mocker):
        obj = MagicMock()
        obj.kind = "Secret"
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=obj)
        with pytest.raises(ValueError, match="Unsupported kind"):
            poll_rollout_status(obj)

    def test_custom_condition_overrides_default(self, mocker):
        obj = _statefulset(desired=3, ready=0)  # default would be not-ready
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=obj)
        assert poll_rollout_status(obj, condition=lambda o: True) is True

    def test_deployment_partial_rollout_is_not_ready(self, mocker):
        obj = MagicMock()
        obj.kind = "Deployment"
        obj.spec.replicas = 3
        obj.status.available_replicas = 2
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=obj)
        assert poll_rollout_status(obj) is False

    def test_deployment_all_replicas_available_is_ready(self, mocker):
        obj = MagicMock()
        obj.kind = "Deployment"
        obj.spec.replicas = 3
        obj.status.available_replicas = 3
        mocker.patch.object(k8s_rollout, "get_namespaced", return_value=obj)
        assert poll_rollout_status(obj) is True


# --------------------------------------------------------------------------- #
# wait_for_rollout  (loop around poll_rollout_status)
# --------------------------------------------------------------------------- #
class TestWaitForRollout:
    @pytest.fixture
    def deployment(self):
        return {"metadata": {"namespace": "ns", "name": "x"}, "kind": "StatefulSet"}

    async def test_returns_once_ready(self, mocker, deployment):
        mocker.patch.object(k8s_rollout, "k8s_obj_to_dict", return_value=deployment)
        mocker.patch.object(k8s_rollout, "poll_rollout_status", return_value=True)
        sleep = mocker.patch.object(k8s_rollout.asyncio, "sleep", new_callable=AsyncMock)

        await wait_for_rollout(deployment, api_client=MagicMock())

        sleep.assert_not_called()

    async def test_polls_until_ready(self, mocker, deployment):
        mocker.patch.object(k8s_rollout, "k8s_obj_to_dict", return_value=deployment)
        poll = mocker.patch.object(
            k8s_rollout, "poll_rollout_status", side_effect=[False, False, True]
        )
        sleep = mocker.patch.object(k8s_rollout.asyncio, "sleep", new_callable=AsyncMock)

        await wait_for_rollout(deployment, api_client=MagicMock())

        assert poll.call_count == 3
        assert sleep.call_count == 2

    async def test_timeout_raises(self, mocker, deployment):
        mocker.patch.object(k8s_rollout, "k8s_obj_to_dict", return_value=deployment)
        mocker.patch.object(k8s_rollout, "poll_rollout_status", return_value=False)
        mocker.patch.object(k8s_rollout.asyncio, "sleep", new_callable=AsyncMock)

        with pytest.raises(TimeoutError):
            await wait_for_rollout(deployment, api_client=MagicMock(), timeout=-1)

    async def test_api_exception_is_retried(self, mocker, deployment):
        mocker.patch.object(k8s_rollout, "k8s_obj_to_dict", return_value=deployment)
        poll = mocker.patch.object(
            k8s_rollout, "poll_rollout_status", side_effect=[ApiException(), True]
        )
        sleep = mocker.patch.object(k8s_rollout.asyncio, "sleep", new_callable=AsyncMock)

        await wait_for_rollout(deployment, api_client=MagicMock())

        assert poll.call_count == 2
        sleep.assert_awaited_once()
