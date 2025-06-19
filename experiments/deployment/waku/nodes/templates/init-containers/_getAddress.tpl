{{- define "waku.nodes.getAddress" -}}
- name: grabaddress
  image: {{ default  "soutullostatus/getaddress" .Values.waku.initContainers.getAddress.repo }}: {{ default "v0.1.0" .Values.waku.getAddress.tag }}
  imagePullPolicy: IfNotPresent
  volumeMounts:
    - name: address-data
      mountPath: /etc/addrs
  command:
    - /app/getaddress.sh
  args:
    - {{ include "ensureQuoted" (default "1" .Values.initContainers.getAddress.numAddrs) }}
    - {{ default "" .Values.initContainers.getAddress.serviceName }}
{{- end }}