# The cluster side a C.R.I.S.S.P. product's chart (crissp/deploy/helm/app) needs, on the Kubernetes provider only: no
# cloud provider's resources. The provider version is pinned exactly; a change of it is a reviewed commit.
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "= 2.38.0"
    }
  }
}
