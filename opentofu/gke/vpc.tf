# VPC
resource "google_compute_network" "vpc" {
  name = "${var.project_id}-vpc"

  auto_create_subnetworks  = false
  enable_ula_internal_ipv6 = true
}

# Subnet
resource "google_compute_subnetwork" "subnet" {
  name   = "${var.project_id}-subnet"
  region = var.region

  ip_cidr_range = "10.0.0.0/16"

  stack_type       = "IPV4_IPV6"
  ipv6_access_type = "EXTERNAL"

  network = google_compute_network.vpc.name
  secondary_ip_range {
    range_name    = "services-range"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "pod-ranges"
    ip_cidr_range = "10.4.0.0/16"
  }
}
