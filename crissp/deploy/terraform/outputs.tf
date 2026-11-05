output "namespace" {
  description = "The namespace the chart is installed in."
  value       = kubernetes_namespace_v1.product.metadata[0].name
}

output "pull_secret_name" {
  description = "The image pull secret's name, for the chart's imagePullSecrets (empty when Terraform made none)."
  value       = var.create_pull_secret ? kubernetes_secret_v1.pull[0].metadata[0].name : ""
}

output "default_deny" {
  description = "Whether the namespace denies all traffic the chart's NetworkPolicies do not allow."
  value       = var.default_deny
}
