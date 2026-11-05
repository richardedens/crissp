variable "kubeconfig_path" {
  description = "Path to the kubeconfig that reaches the cluster (crissp/deploy.sh passes the one it found)."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "The kubeconfig context of the cluster (deploy.json cluster.kubeContext); never the current one by accident."
  type        = string
}

variable "namespace" {
  description = "The product's namespace (deploy.json cluster.namespace)."
  type        = string
}

variable "labels" {
  description = "Extra labels on the namespace, e.g. app.kubernetes.io/part-of."
  type        = map(string)
  default     = {}
}

variable "pod_security" {
  description = "The Pod Security Standard enforced in the namespace: restricted (the chart meets it), baseline or privileged."
  type        = string
  default     = "restricted"

  validation {
    condition     = contains(["restricted", "baseline", "privileged"], var.pod_security)
    error_message = "pod_security must be restricted, baseline or privileged."
  }
}

variable "pull_secret_name" {
  description = "The name of the image pull secret in the namespace (deploy.json cluster.pullSecret.name)."
  type        = string
  default     = "registry-credentials"
}

variable "create_pull_secret" {
  description = "Whether Terraform makes the pull secret; false when it already exists or the registry is public."
  type        = bool
  default     = false
}

variable "registry_server" {
  description = "The registry's host name for the pull secret, e.g. registry.example.org."
  type        = string
  default     = ""
}

variable "registry_username" {
  description = "The registry user for the pull secret; from .env.production through a private file, never in a tfvars in git."
  type        = string
  default     = ""
  sensitive   = true
}

variable "registry_password" {
  description = "The registry password or token for the pull secret; from .env.production through a private file, never in git."
  type        = string
  default     = ""
  sensitive   = true
}

variable "default_deny" {
  description = "Whether the namespace gets a NetworkPolicy that denies all traffic not allowed by the chart's own policies."
  type        = bool
  default     = true
}

variable "quota" {
  description = "The namespace's ResourceQuota: the most every pod together may request and use."

  type = object({
    requests_cpu    = string
    requests_memory = string
    limits_cpu      = string
    limits_memory   = string
    pods            = number
    pvcs            = number
    storage         = string
  })

  default = {
    requests_cpu    = "2"
    requests_memory = "4Gi"
    limits_cpu      = "4"
    limits_memory   = "8Gi"
    pods            = 20
    pvcs            = 5
    storage         = "50Gi"
  }
}

variable "container_defaults" {
  description = "The namespace's LimitRange: what a container gets when it names no requests or limits of its own."

  type = object({
    request_cpu    = string
    request_memory = string
    limit_cpu      = string
    limit_memory   = string
  })

  default = {
    request_cpu    = "50m"
    request_memory = "64Mi"
    limit_cpu      = "500m"
    limit_memory   = "512Mi"
  }
}
