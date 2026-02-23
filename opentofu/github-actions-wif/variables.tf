variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "github_org" {
  description = "GitHub organization or username"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "service_account_id" {
  description = "Service account ID for GitHub Actions"
  type        = string
  default     = "github-actions-tofu"
}

variable "wif_pool_id" {
  description = "Workload Identity Pool ID"
  type        = string
  default     = "github"
}

variable "wif_provider_id" {
  description = "Workload Identity Provider ID"
  type        = string
  default     = "github"
}

variable "sa_project_roles" {
  description = "List of IAM roles to grant to the service account at the project level"
  type        = list(string)
  default = [
    "roles/container.admin",
    "roles/compute.networkAdmin",
    "roles/iam.serviceAccountUser",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/artifactregistry.admin"
  ]
}

