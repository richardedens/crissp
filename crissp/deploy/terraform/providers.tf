# The cluster is named by its kubeconfig and context, never by an address in this repository.
provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.kube_context
}
