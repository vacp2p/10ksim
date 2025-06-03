{{- define "waku.nodes.getEnr" -}}
{{- $values := .Values }}
- name: grabenr
  image: {{ default  "soutullostatus/getenr" $values.getEnr.repo }}:{{ default "v0.5.0" .Values.getEnr.tag }}
  imagePullPolicy: IfNotPresent
  volumeMounts:
    - name: enr-data
      mountPath: /etc/enr
  command:
    - /app/getenr.sh
  args:
  # Check to make sure the number of environment variables matches the numEnrs arg we give to the shell script.
  # TODO [waku-regression-nodes sanity checks]: add this same sanity check to getAddress.tpl.
{{- if not ($values.command.full).container }}
{{- if ($values.command.full).waku }}
  {{ include "assertFlagCountInCommand" ( dict
      "command" $values.command.full.waku
      "flag" "--discv5-bootstrap-node"
      "expectedCount" (default 3 $values.getEnr.numEnrs)) | indent 2 }}
  {{ else }}
    {{- $preset := $values.command.type | default "basic" }}
    {{- $wakuCommand := include "command.genArgs" ( dict
      "args" $values.command.args
      "presets" $values.command.presets
      "preset" $preset)  | indent 4 }}
    {{- include "assertFlagCountInCommand" ( dict
      "command" $wakuCommand
      "flag" "--discv5-bootstrap-node"
      "expectedCount" (default 3 $values.getEnr.numEnrs)) | indent 2}}
  {{- end }}
{{- end }}
    {{- toYaml (list (toString (default 3 $values.names))) | nindent 4 }}
    {{- toYaml (list  ( default "" $values.getEnr.serviceName )) | nindent 4 }}
{{- end }}