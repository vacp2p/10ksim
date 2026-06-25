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


class DeploymentObj:
    def __init__(self, kind, name):
        self.kind = kind
        self.metadata = {"name": name, "namespace": "ns"}


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["serial", "parallel"])
async def test_deploy_orders_base_resources_before_workloads(strategy):
    exp = DummyExperiment.model_construct(
        api_client=Mock(),
        config=DummyCfg(),
        namespace="ns",
    )

    exp._deploy = AsyncMock(return_value=None)

    items = [
        DeploymentObj("Pod", "pod1"),
        DeploymentObj("RoleBinding", "rb1"),
        DeploymentObj("StatefulSet", "sts1"),
        DeploymentObj("ServiceAccount", "sa1"),
        DeploymentObj("Service", "s"),
        DeploymentObj("DaemonSet,", "ds"),
        DeploymentObj("Job,", "j"),
        DeploymentObj("CronJob,", "cj"),
        DeploymentObj("Role", "role1"),
        DeploymentObj("ConfigMap", "cm1"),
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deployments, expected",
    [
        pytest.param(
            [DeploymentObj("ServiceAccount", "sa1"), DeploymentObj("Role", "role1")],
            ["ServiceAccount", "Role"],
            id="list",
        ),
        pytest.param(
            {"sa": DeploymentObj("ServiceAccount", "sa1"), "role": DeploymentObj("Role", "role1")},
            ["ServiceAccount", "Role"],
            id="dict",
        ),
        pytest.param(DeploymentObj("Deployment", "dep1"), ["Deployment"], id="single"),
        pytest.param(
            {
                "outer": [
                    DeploymentObj("ConfigMap", "cm1"),
                    {"inner": DeploymentObj("Service", "svc1")},
                ]
            },
            ["ConfigMap", "Service"],
            id="nested",
        ),
        pytest.param(
            {
                "a": [
                    DeploymentObj("ServiceAccount", "sa1"),
                    {"b": DeploymentObj("RoleBinding", "rb1")},
                ],
                "c": DeploymentObj("Pod", "pod1"),
            },
            ["ServiceAccount", "RoleBinding", "Pod"],
            id="nested_dict_list",
        ),
    ],
)
async def test_deploy_flattens_input_shapes(deployments, expected):
    exp = DummyExperiment.model_construct(
        api_client=Mock(),
        config=DummyCfg(),
        namespace="ns",
    )
    exp._deploy = AsyncMock(return_value=None)

    await exp.deploy(deployments, strategy="serial", timeout=1)

    kinds = [item.kwargs["deployment"].kind for item in exp._deploy.await_args_list]
    assert kinds == expected
