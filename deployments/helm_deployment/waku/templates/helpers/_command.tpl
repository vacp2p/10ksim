{{- define "helpers.container.command" -}}
{{- $values := .values -}}
{{- $command := .command -}}
{{- $hyphenate := true -}}
{{- if hasKey . "hyphenate" }}
  {{- $hyphenate = .hyphenate }}
{{- end }}

{{- if $values.full }}
  {{ $values.full }}
{{- else }}
- sh
- -c
- |
  {{ $command }} \
    {{- $preset := $values.type }}
    {{- include "command.genArgs" (dict
      "args" $values.args
      "presets" $values.presets
      "preset" $preset
      "hyphenate" $hyphenate
      ) | nindent 4 }}
{{- end }}
{{- end }}