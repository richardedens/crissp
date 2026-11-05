# The namespace, with the Pod Security Standard the chart meets.
resource "kubernetes_namespace_v1" "product" {
  metadata {
    name = var.namespace

    labels = merge(var.labels, {
      "app.kubernetes.io/managed-by"       = "terraform"
      "pod-security.kubernetes.io/enforce" = var.pod_security
      "pod-security.kubernetes.io/audit"   = var.pod_security
      "pod-security.kubernetes.io/warn"    = var.pod_security
    })
  }
}

# The image pull secret, from variables only (a private file deploy.sh writes from .env.production, or TF_VAR_*).
resource "kubernetes_secret_v1" "pull" {
  count = var.create_pull_secret ? 1 : 0

  metadata {
    name      = var.pull_secret_name
    namespace = kubernetes_namespace_v1.product.metadata[0].name
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        (var.registry_server) = {
          username = var.registry_username
          password = var.registry_password
          auth     = base64encode("${var.registry_username}:${var.registry_password}")
        }
      }
    })
  }
}

# Nothing in, nothing out, unless one of the chart's NetworkPolicies allows it.
resource "kubernetes_network_policy_v1" "default_deny" {
  count = var.default_deny ? 1 : 0

  metadata {
    name      = "default-deny"
    namespace = kubernetes_namespace_v1.product.metadata[0].name
  }

  spec {
    pod_selector {}
    policy_types = ["Ingress", "Egress"]
  }
}

# The most the namespace may take from the cluster.
resource "kubernetes_resource_quota_v1" "product" {
  metadata {
    name      = "quota"
    namespace = kubernetes_namespace_v1.product.metadata[0].name
  }

  spec {
    hard = {
      "requests.cpu"           = var.quota.requests_cpu
      "requests.memory"        = var.quota.requests_memory
      "limits.cpu"             = var.quota.limits_cpu
      "limits.memory"          = var.quota.limits_memory
      "pods"                   = var.quota.pods
      "persistentvolumeclaims" = var.quota.pvcs
      "requests.storage"       = var.quota.storage
    }
  }
}

# What a container gets when it names no resources of its own (the quota then still holds).
resource "kubernetes_limit_range_v1" "product" {
  metadata {
    name      = "defaults"
    namespace = kubernetes_namespace_v1.product.metadata[0].name
  }

  spec {
    limit {
      type = "Container"

      default_request = {
        cpu    = var.container_defaults.request_cpu
        memory = var.container_defaults.request_memory
      }

      default = {
        cpu    = var.container_defaults.limit_cpu
        memory = var.container_defaults.limit_memory
      }
    }
  }
}
