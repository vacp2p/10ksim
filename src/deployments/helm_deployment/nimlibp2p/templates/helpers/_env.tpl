{{/*
env.genVars

Generates environment variable entries from user overrides and preset values.
- Accepts a dict with:
    - "args": map of user-supplied values (can be empty or undefined).
    - "presets": map of preset sets (e.g., .Values.presets).
    - "preset": name of the preset to use.
- For each unique key in either `args` or the selected preset:
    - If the value is nil, adds `- name: KEY` with empty string value
    - If the value is a list, creates a single env entry with colon-separated values
    - Otherwise, creates a single env entry

Usage:
  {{ include "env.genVars" (dict "args" .Values.env.args "presets" .Values.presets "preset" .Values.preset) }}

Example output:
- name: NUM
  value: 1000
- name: PATHS
  value: "dir1:dir2:dir3"
*/}}
{{- define "env.genVars" }}
  {{- $args := .args | default (dict) }}
  {{- $presets := .presets | default (dict) }}
  {{- $presetName := .preset | default "" }}
  {{- $preset := (index $presets $presetName) | default (dict) }}

  {{- /* Collect all unique keys from both $preset and $args */}}
  {{- $allKeys := dict }}
  {{- range $key, $_ := $preset }}
    {{- $_ := set $allKeys $key true }}
  {{- end }}
  {{- range $key, $_ := $args }}
    {{- $_ := set $allKeys $key true }}
  {{- end }}

  {{- /* Iterate over all collected keys */}}
  {{- range $key, $_ := $allKeys }}
    {{- $use_key := false }}
    {{- $value := "" }}
    {{- if hasKey $args $key }}
      {{- $use_key = true }}
      {{- $value = index $args $key }}
    {{- else if hasKey $preset $key }}
      {{- $use_key = true }}
      {{- $value = index $preset $key }}
    {{- end }}


    {{- if $use_key }}
      {{- $envName := upper $key }}
      {{- if kindIs "slice" $value }}
        {{- $joined := join ":" $value }}
- name: {{ $envName }}
  value: {{ quote (toString $joined) }}
      {{- else }}
- name: {{ $envName }}
  value: {{ quote (toString $value) }}
      {{- end }}
    {{- end }}
    {{- /* else, do not output anything for missing keys */}}
  {{- end }}
{{- end }}