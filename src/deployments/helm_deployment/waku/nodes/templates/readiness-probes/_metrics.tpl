{{- define "waku.nodes.readiness-probe.metrics" -}}
- /bin/sh
- -c
- |
  curl_output=$(curl -s http://127.0.0.1:8008/metrics);
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
{{- end }}