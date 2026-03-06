{{- define "waku.nodes.readiness-probe.jswaku" -}}
- /bin/sh
- -c
- |
  node=127.0.0.1
  jswaku_external_port=8080
  curl -s -X GET http://$node:${jswaku_external_port}/waku/v1/peer-info \
      -H "Content-Type: application/json" | grep 'peerId' > /dev/null
{{- end }}