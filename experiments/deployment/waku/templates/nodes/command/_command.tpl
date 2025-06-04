{{- define "waku.container.command" -}}
{{- if .Values.waku.container.command }}
  {{ .Values.waku.container.command }}
{{ else }}
- sh
- -c
- |
{{- if .Values.includes.getAddress }}
  . /etc/addrs/addrs.env
  echo addrs are{{- range $i, $ := until (int .Values.waku.getAddr.numEnrs) }} $ENR{{ add1 $i }}{{- end }}
{{- end }}
{{- if .Values.includes.getEnr }}
  . /etc/enr/enr.env
  echo ENRs are{{- range $i, $ := until (int .Values.waku.getEnr.numEnrs) }} $ENR{{ add1 $i }}{{- end }}
{{- end }}

  {{- if .Values.waku.command.full }}
    {{- .Values.waku.command.full | indent 1 }}
  {{- else }}
  {{- if .Values.waku.command.sleep }}
  sleep 10
  {{- end }} # End sleep.
  nice -n 19 /usr/bin/wakunode
    {{- $preset := .Values.waku.command.type | default "basic" }}
    {{- include "command.genArgs" (dict "args" .Values.waku.command.args "presets" .Values.waku.command.presets "preset" $preset)  | indent 4 }}
  {{- end }} # End full command.
{{- end }} # End container command.
{{- end }} # End definition.