resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = "application-images"
  description   = "Docker image repository for containers running in GKE"
  format        = "DOCKER"

  cleanup_policies {
    id     = "delete-old-images"
    action = "DELETE"

    condition {
      older_than = "2592000s" # 30 days in seconds
      tag_state  = "UNTAGGED"
    }
  }

  cleanup_policies {
    id     = "keep-recent-tagged"
    action = "KEEP"

    most_recent_versions {
      keep_count = 10
    }
  }

  project = var.project_id
}
