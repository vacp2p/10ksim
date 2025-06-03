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

{{/*
command.genArgs

Generates command-line arguments from a combination of user overrides and preset values.
- Accepts a dict with:
    - "args": map of user-supplied arguments (can be empty or undefined).
    - "presets": map of preset argument sets (e.g., .Values.presets).
    - "preset": name of the preset to use.
- For each unique key in either `args` or the selected preset:
    - If the value is nil or empty, outputs a switch: --flag
    - If the value is a list, outputs multiple: --flag="item" (one per list item)
    - If the value is already quoted, outputs as is: --flag="value"
    - Otherwise, quotes the value: --flag="value"
    - `value` is from `args` if in `args`, otherwise from the preset.
- Does **not** add a trailing backslash.
- Handles missing/undefined input gracefully.

Usage:
  {{ include "command.genArgs" (dict "args" .Values.command.args "presets" .Values.presets "preset" .Values.preset) }}

Example output:
  --log-level="INFO"
  --max-connections="200"
  --enable-debug
  --discv5BootstrapNode="$ENR1"
  --discv5BootstrapNode="$ENR2"
*/}}
{{- define "command.genArgs" -}}
{{- $args := .args | default dict }}
{{- $presets := .presets | default dict }}
{{- $presetName := .preset | default "" }}
{{- $preset := (index $presets $presetName) | default dict }}

{{- $allKeys := dict }}
{{- range $key, $value := $preset }}
  {{- $_ := set $allKeys $key true }}
{{- end }}
{{- range $key, $value := $args }}
  {{- $_ := set $allKeys $key true }}
{{- end }}

{{- $keys := list }}
{{- range $key, $_ := $allKeys }}
  {{- $keys = append $keys $key }}
{{- end }}

{{- range $i, $key := $keys }}
  {{- $value := (index $args $key) | default (index $preset $key) }}
  {{- $flag := include "toHyphenCase" $key }}
  {{- if eq $value nil }}
--{{ $flag }}
  {{- else if kindIs "slice" $value }}
    {{- range $item := $value }}
--{{ $flag }}={{ include "ensureQuoted" $item }}
    {{- end }}
  {{- else }}
--{{ $flag }}={{ include "ensureQuoted" $value }}
  {{- end }}
{{- end }}
{{- end }}


{{/*
ensureQuoted

Ensures that the input string is quoted.
If it is, return the input string.
Otherwise, return the input string with quotes.

Usage:
  {{ include "ensureQuoted" $value }}

Examples:
  Input:  foo         → Output:  "foo"
  Input:  "bar"       → Output:  "bar"
  Input:  hello world → Output:  "hello world"
*/}}
{{- define "ensureQuoted" -}}
{{- $val := toString . -}}
{{- if and (hasPrefix "\"" $val ) (hasSuffix "\"" $val ) -}}
{{ $val }}
{{- else -}}
"{{ $val }}"
{{- end -}}
{{- end -}}