{{/*
valueOrPreset

Returns .value if it is set (not nil, not empty).
Otherwise, checks the value from .presets[.presetKey]:
  - If it starts with "include:", treats the rest as a template name and includes it.
  - Otherwise, returns the preset value.

Optionally, pass `"asYaml": true` to serialize the result as YAML (allowing for piping to `fromYaml`).
If `"asYaml"` is omitted or false, the result is returned as a string (for direct YAML insertion).

Parameters:
  .value      - The direct value to use if set
  .presetKey  - The key to use for the preset
  .presets    - Map of preset values or template references (e.g., from values.yaml)
  .asYaml     - (optional, bool) If true, output is YAML (for use with `fromYaml`); if false or omitted, output is a string

Usage:
  # For direct YAML insertion (string result):
  {{ include "valueOrPreset" (dict "value" .Values.container.command "presetKey" .Values.type "presets" .Values.commandPresets) }}

  # For dictionary/object use (YAML result, e.g., for fromYaml):
  {{- $myDict := (include "valueOrPreset" (dict "value" .Values.command "presetKey" .Values.type "presets" .Values.presets "asYaml" true) | fromYaml) }}

Examples:
  # In values.yaml:
  commandPresets:
    type_1: "include:commandTemplateType1"
    type_2: "echo Goodbye"

  # In _helpers.tpl:
  {{- define "commandTemplateType1" -}}
  echo "Hello from template 1"
  {{- end }}

  # In template:
  {{ include "valueOrPreset" (dict "value" .Values.container.command "presetKey" .Values.type "presets" .Values.commandPresets) }}
*/}}
{{- define "valueOrPreset" -}}
{{- $value := .value -}}
{{- $presetKey := .presetKey -}}
{{- $presets := .presets -}}
{{- $asYaml := .asYaml | default false -}}
{{- $result := "" -}}
{{- if $value }}
  {{- $result = $value }}
{{- else }}
  {{- $presetValue := index $presets $presetKey }}
  {{- if and $presetValue (kindIs "string" $presetValue) (hasPrefix "include:" $presetValue) }}
    {{- $tplName := trimPrefix "include:" $presetValue | trim }}
    {{- $result = include $tplName . }}
  {{- else if $presetValue }}
    {{- $result = $presetValue }}
  {{- end }}
{{- end }}
{{- if $asYaml }}
{{- toYaml $result }}
{{- else }}
{{- $result }}
{{- end }}
{{- end }}



{{/*
applyAll

- Outputs .value if it is set (not nil, not empty).
- For each item in .list (if set), looks up the value in .dict:
    - If the value starts with "include:", treats the rest as a template name and includes it.
    - Otherwise, outputs the value as a string.

Parameters:
  .value  - A single value to output if set.
  .dict   - A dictionary (map) of key-value pairs or template references.
  .list   - A list of keys to look up in .dict. If not set, treated as an empty list.

Usage:
  {{ include "applyAll" (dict
      "value" .Values.current.sportTool
      "dict" (dict "baseball" "bat" "hockey" "stick" "bowling" "include:bowlingTemplate")
      "list" .Values.current.sports
  ) }}

Example:
  If .Values.current.sportTool is "helmet", and .Values.current.sports is ["baseball", "bowling"], output:
    helmet
    bat
    [contents of bowlingTemplate]

*/}}
{{- define "applyAll" -}}
{{- $value := .value -}}
{{- $dict := .dict -}}
{{- $list := .list | default (list) -}}
{{- if $value }}
{{ $value }}
{{- end }}
{{- range $item := $list }}
  {{- $dictVal := index $dict $item }}
  {{- if $dictVal }}
    {{- if hasPrefix "include:" $dictVal }}
      {{- $tplName := trimPrefix "include:" $dictVal | trim }}
      {{- include $tplName . }}
    {{- else }}
{{ $dictVal }}
    {{- end }}
  {{- end }}
{{- end }}
{{- end }}


{{/*
assertFlagCountInCommand

Asserts that the number of times a given flag (e.g., "--flag1") appears in a command string equals the expected count.
Fails template rendering if not.

Parameters:
  .command         (string) - The command string to check.
  .flag            (string) - The flag to search for (e.g., "--flag1").
  .expectedCount   (int)    - The expected number of times the flag should appear.

Usage:
  {{ include "assertFlagCountInCommand" (dict
      "command" .Values.command
      "flag" "--flag1"
      "expectedCount" .Values.expectedNumFlags
  ) }}
*/}}
{{- define "assertFlagCountInCommand" -}}
{{- $command := .command | toString -}}
{{- $flag := .flag | toString -}}
{{- $expectedCount := .expectedCount | int -}}

{{- $pattern := printf "(^|\\s)%s(\\s|=|$)" $flag -}}
{{- $matches := regexFindAll $pattern $command -1 -}}
{{- $actualCount := len $matches -}}

{{- if ne $expectedCount $actualCount }}
  {{- fail (printf "Assertion failed: expected %d instances of flag '%s' in command, but found %d" $expectedCount $flag $actualCount) }}
{{- end }}
{{- end }}


{{/*
map.keepTrue

Given a dictionary, return a new dictionary comprised of all key value pairs for which value is true.

Usage:
  {{ include "map.keepTrue" .Values.shouldInclude }}
*/}}
{{- define "map.keepTrue" -}}
{{- $out := dict -}}
{{- range $key, $value := . }}
  {{- if $value }}
    {{- $out = set $out $key $value }}
  {{- end }}
{{- end }}
{{- toYaml $out }}
{{- end }}