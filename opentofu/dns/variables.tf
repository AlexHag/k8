variable "project_id" {
  description = "project id"
  type        = string
}

variable "region" {
  description = "region"
  type        = string
}

variable "fully_qualified_domain_name" {
  description = "Fully qualified domain name for the DNS records that points to the Envoy Gateway LB"
  type        = string
}