variable "project_id" {
  description = "project id"
  type        = string
}

variable "enabled_services" {
  description = "List of GCP services to enable"
  type        = list(string)
}