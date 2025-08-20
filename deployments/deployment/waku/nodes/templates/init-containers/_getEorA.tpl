{{/*
waku.nodes.getEorA

Generates initContainer section for getEnr or getAddress.
Args dict:
  "values": .Values.waku.nodes
  "type": Either "enr" or "address"

This function also checks that the number of flags match the "num" field of values.

type    | flag
--------------
enr     | --discv5-bootstrap-node
address | --lightpushnode

If $values.getEnr.num is 5, then there should be 5 --discv5-bootstrap-node flags.
This check is not applied when the full container command is given with $values.command.full).container

Usage:
  {{- include "waku.nodes.getEorA" ( dict "values" .Values.waku.nodes "type" "address" ) | nindent 8 }}

*/}}
{{- define "waku.nodes.getEorA" -}}
{{- $values := .values }}
{{- $type := .type }}
{{- $settings := dict
    "address" (dict "shortname" "addrs" "version" "v0.1.0" "image" "soutullostatus/getaddress" "flag" "--lightpushnode")
    "enr"     (dict "shortname" "enr"  "version" "v0.5.0" "image" "soutullostatus/getenr" "flag" "--discv5-bootstrap-node")
}}
{{- $cfg := index $settings $type }}
{{- if not $cfg }}
{{- fail (printf "Unknown type: %s" $type) }}
{{- end }}

# Set subvalues to `$values.getEnr` or `$values.getAddress`.
{{- $key := printf "get%s" ($type | title) }}
{{- $subvalues := index $values $key }}

- name: {{ printf "grab%s" $type }}
  image: {{ default $cfg.image $subvalues.repo }}:{{ default $cfg.version $subvalues.tag }}
  imagePullPolicy: IfNotPresent
  volumeMounts:
    - name: {{ printf "%s-data" $type }}
      mountPath: {{ printf "/etc/%s" $cfg.shortname }}
  command:
    - {{ printf "/app/get%s.sh" $type }}
  args:
# Check to make sure the number of environment variables matches the numEnrs arg we give to the shell script.
# TODO [waku-regression-nodes sanity checks]: add this same sanity check to getAddress.tpl.
{{- if not ($values.command.full).container }}
{{- if ($values.command.full).waku }}
  {{ include "assertFlagCountInCommand" ( dict
      "command" $values.command.full.waku
      "flag" $cfg.flag
      "expectedCount" (default 3 $subvalues.num)) | indent 2 }}
  {{ else }}
    {{- $preset := $values.command.type | default "basic" }}
    {{- $wakuCommand := include "command.genArgs" ( dict
      "args" $values.command.args
      "presets" $values.command.presets
      "preset" $preset)  | indent 4 }}
    {{- include "assertFlagCountInCommand" ( dict
      "command" $wakuCommand
      "flag" $cfg.flag
      "expectedCount" (default 3 $subvalues.num)) | indent 2}}
  {{- end }}
{{- end }}
    {{- toYaml (list (toString (default 3 $subvalues.num))) | nindent 4 }}
    {{- toYaml (list  ( default "" $subvalues.serviceName )) | nindent 4 }}
{{- end }}
