from typing import List

from kubernetes.client import V1ExecAction, V1Probe
from pydantic import PositiveInt


def readiness_probe_command_metrics(num_topics: PositiveInt = 1) -> List[str]:
    prefix = ["/bin/sh", "-c"]
    command_block = """curl_output=$(curl -s http://127.0.0.1:8008/metrics);
curl_status=$?;
if [ $curl_status -ne 0 ]; then
  echo "Curl failed with status $curl_status";
  exit 1;  # failure, unhealthy state
fi;
echo "$curl_output" | awk '
  !/^#/ && /^libp2p_gossipsub_healthy_peers_topics / {{
    print "Found gossipsub:", $0;
    if ($2 == {:.1f}) {{
      exit 0;  # success, healthy state
    }} else {{
      exit 1;  # failure, unhealthy state
    }}
  }}
  END {{ if (NR == 0) exit 1 }}  # If no matching line is found, exit with failure
'
""".format(
        num_topics
    )
    return prefix + [command_block]


def readiness_probe_metrics():
    return V1Probe(
        _exec=V1ExecAction(command=readiness_probe_command_metrics(num_topics=1)),
        success_threshold=5,
        initial_delay_seconds=5,
        period_seconds=1,
        failure_threshold=2,
        timeout_seconds=5,
    )
