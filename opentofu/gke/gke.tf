resource "google_container_cluster" "gke" {
  name = "${var.project_id}-gke"

  location = var.region

  enable_autopilot         = true
  enable_l4_ilb_subsetting = true

  network    = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.subnet.id

  # Enable DNS-based control plane access.
  control_plane_endpoints_config {
    dns_endpoint_config {
      allow_external_traffic = true
    }
  }

  ip_allocation_policy {
    stack_type                    = "IPV4_IPV6"
    services_secondary_range_name = google_compute_subnetwork.subnet.secondary_ip_range[0].range_name
    cluster_secondary_range_name  = google_compute_subnetwork.subnet.secondary_ip_range[1].range_name
  }

  # Configure Workload Identity Federation
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Enable Secret Manager addon
  secret_manager_config {
    enabled = true
  }

  # Set `deletion_protection` to `true` will ensure that one cannot
  # accidentally delete this instance by use of Terraform.
  deletion_protection = false
}