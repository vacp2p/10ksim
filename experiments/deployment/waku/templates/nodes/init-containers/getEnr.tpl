{{- define "waku.nodes.getEnr" -}}
- name: grabenr
  image: {{ default  "soutullostatus/getenr" .Values.waku.getEnr.repo }}:{{ default "v0.5.0" .Values.waku.getEnr.tag }}
  imagePullPolicy: IfNotPresent
  volumeMounts:
    - name: enr-data
      mountPath: /etc/enr
  command:
    - /app/getenr.sh
  args:
  # Check to make sure the number of environment variables matches the numEnrs arg we give to the shell script.
  # TODO: add this same sanity check to getAddress.tpl.
{{- if not .Values.waku.container.command }}
{{- if .Values.waku.command.full }}
  {{ include "assertFlagCountInCommand" ( dict
      "command" .Values.waku.container.command
      "flag" "--discv5BootstrapNode"
      "expectedCount" (default 3 .Values.getEnr.numEnrs)) | indent 2 }}
  {{ else }}
  {{- $preset := .Values.waku.command.type | default "basic" }}
  {{ include "assertPresetListLength" ( dict
              "presets" .Values.waku.command.presets
              "presetName" $preset
              "path" "discv5BootstrapNode"
              "expectedCount" (default 3 .Values.getEnr.numEnrs)
              )
  }}
  {{- end }}
{{- end }}
    {{- toYaml (list (toString (default 3 .Values.names))) | nindent 4 }}
    {{- toYaml (list  ( default "" .Values.waku.getEnr.serviceName )) | nindent 4 }}
{{- end }}