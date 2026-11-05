{{- define "app.name" -}}{{ .Values.product | default .Chart.Name }}{{- end }}
{{- define "app.labels" -}}
app.kubernetes.io/name: {{ include "app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.version | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
{{- define "app.selector" -}}
app.kubernetes.io/name: {{ include "app.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
{{/* A pod that runs as the given user, never as root, with the runtime's seccomp profile and no API token. */}}
{{- define "app.pod" -}}
automountServiceAccountToken: false
securityContext: {runAsNonRoot: true, runAsUser: {{ .uid }}, runAsGroup: {{ .uid }}, fsGroup: {{ .uid }}, fsGroupChangePolicy: OnRootMismatch, seccompProfile: {type: RuntimeDefault}}
{{- with .root.Values.imagePullSecrets }}
imagePullSecrets: {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
{{/* A container that may not escalate, holds no capabilities and cannot write its own file system. */}}
{{- define "app.secure" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  capabilities: {drop: ["ALL"]}
{{- end }}
{{/* The writable folders of a container (its root file system is read-only): mounts, then volumes. */}}
{{- define "app.writableMounts" -}}
{{- range $i, $p := . }}
- {name: {{ printf "w%d" $i }}, mountPath: {{ $p }}}
{{- end }}
{{- end }}
{{- define "app.writableVolumes" -}}
{{- range $i, $p := . }}
- {name: {{ printf "w%d" $i }}, emptyDir: {}}
{{- end }}
{{- end }}
{{/* The Traefik Middlewares on the product's Ingress, as router.middlewares wants them. */}}
{{- define "app.middlewares" -}}
{{- $m := list }}
{{- if .Values.ingress.securityHeaders.enabled }}{{ $m = append $m (printf "%s-%s-headers@kubernetescrd" .Release.Namespace .Release.Name) }}{{ end }}
{{- if .Values.ingress.maxRequestBodyBytes }}{{ $m = append $m (printf "%s-%s-body-size@kubernetescrd" .Release.Namespace .Release.Name) }}{{ end }}
{{- if .Values.ingress.rateLimit }}{{ $m = append $m (printf "%s-%s-ratelimit@kubernetescrd" .Release.Namespace .Release.Name) }}{{ end }}
{{- join "," $m }}
{{- end }}
{{/* The parts that serve requests, as a list of component names. */}}
{{- define "app.served" -}}
{{- $c := list }}
{{- if .Values.backend.enabled }}{{ $c = append $c "backend" }}{{ end }}
{{- if .Values.frontend.enabled }}{{ $c = append $c "frontend" }}{{ end }}
{{- join "," $c }}
{{- end }}
