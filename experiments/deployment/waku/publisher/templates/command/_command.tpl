{{- define "waku.publisher.container.command" -}}
{{- $values := .values -}}
{{- if $values.full }}
  {{ $values.full }}
{{- else }}
- sh
- -c
- |
  python /app/traffic.py
    {{- $preset := $values.type }}
    {{- print " --protocols" }}
    {{- $protocolDict := (include "valueOrPreset" (dict
      "value" $values.protocols
      "presetKey" $preset
      "presets" $values.protocolPresets
      "asYaml" true
      )) | fromYaml }}
    {{- $protocolDict = (include "map.keepTrue" $protocolDict) | fromYaml }}
    {{- range $protocol, $_ := $protocolDict }} {{ $protocol }} {{- end }}
    {{- printf " \\" -}}
    {{- include "command.genArgs" (dict
      "args" $values.args
      "presets" $values.presets
      "preset" $preset
      ) | nindent 4 }}
{{- end }}
{{- end }}