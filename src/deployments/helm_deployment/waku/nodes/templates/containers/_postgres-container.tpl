{{- define "waku.nodes.postgress.container" -}}
- name: postgres
image: postgres:15.1-alpine
imagePullPolicy: IfNotPresent
volumeMounts:
  - name: postgres-data
    mountPath: /var/lib/postgresql/data
env:
  - name: POSTGRES_DB
    value: wakumessages
  - name: POSTGRES_USER
    value: wakuuser
  - name: POSTGRES_PASSWORD
    value: wakupassword
ports:
  - containerPort: 5432
readinessProbe:
  exec:
    command:
      - sh
      - -c
      - |
        pg_isready -U wakuuser -d wakumessages
  initialDelaySeconds: 5
  periodSeconds: 2
  timeoutSeconds: 5
{{- end }}