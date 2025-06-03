{{/*
valueOrPreset

Returns .value if it is set (not nil, not empty).
Otherwise, checks the value from .presets[.presetKey]:
  - If it starts with "include:", treats the rest as a template name and includes it.
  - Otherwise, returns the preset value as a string.

Parameters:
  .value      - The direct value to use if set
  .presetKey  - The key to use for the preset
  .presets    - Map of preset values or template references (e.g., from values.yaml)

Usage:
  {{ include "valueOrPreset" (dict "value" .Values.container.command "presetKey" (default "basic" .Values.type) "presets" .Values.commandPresets) }}

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
{{- if $value }}
  {{- $value }}
{{- else }}
  {{- $presetValue := index $presets $presetKey }}
  {{- if and $presetValue (hasPrefix "include:" $presetValue) }}
    {{- $tplName := trimPrefix "include:" $presetValue | trim }}
    {{- include $tplName .  }}
  {{- else if $presetValue }}
    {{- $presetValue }}
  {{- end }}
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
assertPresetListLength

Asserts that the length of the list (or single value) at .path in the selected preset matches .expectedCount.
Fails template rendering if not.

Parameters:
  .presets   (dict)   - The root dictionary containing all presets (e.g., .Values.presets)
  .presetName    (string) - The name of the preset to use (e.g., "soccer", "basketball")
  .path          (string) - Dot-separated path to the target list (e.g., "sports.equipment.flag1")
  .expectedCount (int)    - The expected number of items

Usage:
  {{ include "assertPresetListLength" (dict
      "presets" .Values.presets
      "presetName" .Values.presetType
      "path" "sports.equipment.flag1"
      "expectedCount" .Values.classroom.numStudents
  ) }}
*/}}
{{- define "assertPresetListLength" -}}
{{- $presets := .presets -}}
{{- $presetName := .presetName -}}
{{- $path := .path -}}
{{- $expectedCount := .expectedCount | int -}}

{{- $preset := index $presets $presetName -}}
{{- $keys := split "." $path -}}
{{- $value := $preset -}}
{{- range $key := $keys }}
  {{- if $value }}
    {{- $value = index $value $key }}
  {{- end }}
{{- end }}

{{- $normList := (list) -}}
{{- if eq (kindOf $value) "slice" }}
  {{- $normList = $value }}
{{- else if $value }}
  {{- $normList = list $value }}
{{- end }}
{{- $actualCount := len $normList -}}

{{- if ne $expectedCount $actualCount }}
  {{- fail (printf "Assertion failed: expected `%d` items at path `%s` in preset `%s`, but found `%d`" $expectedCount $path $presetName $actualCount) }}
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


