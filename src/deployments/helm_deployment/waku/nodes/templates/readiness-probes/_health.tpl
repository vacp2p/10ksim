{{- define "waku.nodes.readiness-probe.health" -}}
- /bin/sh
- -c
- >
  if curl -s http://127.0.0.1:8008/health | grep -q 'OK'; then
    exit 0;  # success, healthy state
  else
    exit 1;  # failure, unhealthy state
  fi
{{- end }}