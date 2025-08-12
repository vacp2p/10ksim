{{/*
toHyphenCase

Converts a lowerCamelCase or PascalCase string to hyphen-case (kebab-case).
For example: "maxConnections" becomes "max-connections".
Useful for mapping YAML/Helm value keys to command-line flag names.

Usage:
  {{ include "toHyphenCase" "maxConnections" }}
*/}}
{{- define "toHyphenCase" -}}
{{- regexReplaceAll "(?m)([a-z0-9])([A-Z])" . "${1}-${2}" | lower -}}
{{- end }}


{{- define "quoteIfNeeded" -}}
  {{- $val := . -}}
  {{- if not (kindIs "string" $val) -}}
    {{- printf "%v" $val -}}
  {{- else -}}
    {{- $str := $val | trim -}}
    {{- if regexMatch "^(['\"]).*\\1$" $str -}}
      {{- /* Already quoted */ -}}
      {{- $val -}}
    {{- else -}}
      {{- if regexMatch "[\\s]" $val -}}
        {{- $escaped := replace $val "\"" "\\\"" -}}
        "{{ $escaped }}"
      {{- else -}}
        {{- $val -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end }}

{{/*
command.genArgs

Generates command-line arguments from user overrides and preset values.
- Accepts a dict with:
    - "args": map of user-supplied arguments (can be empty or undefined).
    - "presets": map of preset argument sets (e.g., .Values.presets).
    - "preset": name of the preset to use.
    - "hyphenate": (optional, default true) if false, disables hyphen-case conversion of argument keys.
- For each unique key in either `args` or the selected preset:
    - If the value is nil or empty, outputs a switch: --flag
    - If the value is a list, outputs multiple: --flag="item" (one per list item)
    - `value` is from `args` if in `args`, otherwise from the preset.

Usage:
  {{ include "command.genArgs" (dict "args" .Values.command.args "presets" .Values.presets "preset" .Values.preset "hyphenate" true) }}

Example output:
--log-level=INFO \
--enable-debug \
--discv5-bootstrap-node=$ENR1 \
--discv5-bootstrap-node=$ENR2
*/}}
{{- define "command.genArgs" -}}
  {{- $args := .args | default dict -}}
  {{- $presets := .presets | default dict -}}
  {{- $presetName := .preset | default "" -}}
  {{- $preset := (index $presets $presetName) | default dict -}}
  {{- $hyphenate := true -}}
  {{- if hasKey . "hyphenate" }}
    {{- $hyphenate = .hyphenate }}
  {{- end }}

  {{- /* Collect all unique keys */ -}}
  {{- $allKeys := dict -}}
  {{- range $key, $value := $preset }} {{- $_ := set $allKeys $key true }} {{- end -}}
  {{- range $key, $value := $args }} {{- $_ := set $allKeys $key true }} {{- end -}}

  {{- /* Convert keys dict to list */ -}}
  {{- $keys := list -}}
  {{- range $key, $_ := $allKeys }} {{- $keys = append $keys $key }} {{- end -}}

  {{- /* Collect all argument lines into a slice */ -}}
  {{- $lines := list -}}
  {{- range $i, $key := $keys }}
    {{- $value := (index $args $key) | default (index $preset $key) -}}
    {{- $flag := $key -}}
    {{- if $hyphenate }}
      {{- $flag = include "toHyphenCase" $key }}
    {{- end }}
    {{- if eq $value nil }}
      {{- $lines = append $lines (printf "--%s" $flag) }}
    {{- else if kindIs "slice" $value }}
      {{- range $item := $value }}
        {{- $arg := printf "--%s=%s" $flag (include "quoteIfNeeded" $item) }}
        {{- $lines = append $lines $arg }}
      {{- end }}
    {{- else }}
      {{- $arg := printf "--%s=%s" $flag (include "quoteIfNeeded" $value) }}
      {{- $lines = append $lines $arg }}
    {{- end }}
  {{- end }}

  {{- /* Print lines with trailing backslash except last */ -}}
  {{- $lastIndex := sub (len $lines) 1 -}}
  {{- range $i, $line := $lines }}
    {{- if lt $i $lastIndex }}
{{- printf "%s \\\n" $line }}
    {{- else }}
{{- printf "%s\n" $line }}
    {{- end }}
{{- end }}

{{- end }}