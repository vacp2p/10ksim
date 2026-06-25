from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from src.deployments.experiments.base_experiment import BaseExperiment


class DummyCfg(BaseModel):
    foo: str = "bar"


class DummyExperiment(BaseExperiment[DummyCfg]):
    config: DummyCfg

    async def _run(self):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["serial", "parallel"])
async def test_deploy_orders_base_resources_before_workloads(strategy):
    exp = DummyExperiment.model_construct(
        api_client=Mock(),
        config=DummyCfg(),
        namespace="ns",
    )

    exp._deploy = AsyncMock(return_value=None)

    class Obj:
        def __init__(self, kind, name):
            self.kind = kind
            self.metadata = {"name": name, "namespace": "ns"}

    items = [
        Obj("Pod", "pod1"),
        Obj("RoleBinding", "rb1"),
        Obj("StatefulSet", "sts1"),
        Obj("ServiceAccount", "sa1"),
        Obj("Service", "s"),
        Obj("DaemonSet,", "ds"),
        Obj("Job,", "j"),
        Obj("CronJob,", "cj"),
        Obj("Role", "role1"),
        Obj("ConfigMap", "cm1"),
    ]

    await exp.deploy(items, strategy=strategy, timeout=1)

    kinds = [c.kwargs["deployment"].kind for c in exp._deploy.await_args_list]

    foundational = {"ServiceAccount", "Role", "ConfigMap", "Service", "RoleBinding"}
    workloads = {
        "Pod",
        "StatefulSet",
        "DaemonSet",
        "Deployment",
        "Job",
        "CronJob",
        "ReplicaSet",
        "ReplicationController",
    }

    foundation_positions = [i for i, k in enumerate(kinds) if k in foundational]
    workload_positions = [i for i, k in enumerate(kinds) if k in workloads]

    assert foundation_positions
    assert workload_positions
    assert max(foundation_positions) < min(workload_positions)
