variable "project_id" {
  description = "GCP project ID where Cloud SQL is provisioned."
  type        = string
}

variable "region" {
  description = "GCP region for the Cloud SQL instance."
  type        = string
}

variable "instance_name" {
  description = "Cloud SQL instance name."
  type        = string
}

variable "database_name" {
  description = "Application database name created inside the instance."
  type        = string
}

variable "database_user" {
  description = "Application database user."
  type        = string
}

variable "db_password_secret_id" {
  description = "Secret Manager secret ID used to store the generated DB password."
  type        = string
}

variable "service_account_id" {
  description = "Google service account ID used by the Kubernetes workload."
  type        = string
}

variable "workload_identity_namespace" {
  description = "Kubernetes namespace used for workload identity binding."
  type        = string
}

variable "workload_identity_ksa_name" {
  description = "Kubernetes service account name used for workload identity binding."
  type        = string
}