
data "google_project" "current" {
  project_id = var.project_id
}

# Google Secret Manager Accessor Service Account for GKE
resource "google_service_account" "ci_builder" {
  account_id   = "artifacts-ci-builder"
  display_name = "GitHub Actions Artifact Registry CI Builder"
  project      = var.project_id
}

# Allow CI/CD to push images
resource "google_artifact_registry_repository_iam_member" "ci_writer" {
  location   = google_artifact_registry_repository.docker.location
  repository = google_artifact_registry_repository.docker.name
  project    = var.project_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci_builder.email}"
}

# Allow Cloud Run / GKE to pull images
resource "google_artifact_registry_repository_iam_member" "runtime_reader" {
  location   = google_artifact_registry_repository.docker.location
  repository = google_artifact_registry_repository.docker.name
  project    = var.project_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_project.current.number}-compute@developer.gserviceaccount.com"
}
