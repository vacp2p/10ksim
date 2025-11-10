{{- define "waku.container.command" -}}
{{- $includes := .includes -}}
{{- $command := .command -}}
{{- if ($command.full).container -}}
  {{ $command.full.container | toYaml }}
{{- else -}}
- sh
- -c
- |
{{- if $includes.getAddress }}
  . /etc/addrs/addrs.env
  echo addrs are{{- range $i, $ := until (int $includes.getAddress.num) }} $addrs{{ add1 $i }}{{- end }}
{{- end }}
{{- if $includes.getEnr }}
  . /etc/enr/enr.env
  echo ENRs are{{- range $i, $ := until (int $includes.getEnr.num) }} $ENR{{ add1 $i }}{{- end }}
{{- end }}

{{- if ($command.full).waku }}
    {{- $command.full.waku | indent 1 }}
{{- else }}
  {{- if $command.sleep }}
  sleep 10
  {{- end }}
  {{- if $command.nice }}
  {{ printf "nice -n %d \\" (int $command.nice) }}
  {{- end }}
  /usr/bin/wakunode \
    {{- $preset := $command.type | default "basic" -}}
    {{- include "command.genArgs" ( dict
      "args" $command.args
      "presets" $command.presets
      "preset" $preset)  | nindent 4 -}}
  {{- end }}
{{- end }}
{{- end }}