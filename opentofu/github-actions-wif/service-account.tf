# GitHub Actions service account used by CI/CD to apply OpenTofu changes
resource "google_service_account" "github_actions" {
  account_id   = var.service_account_id
  display_name = "GitHub Actions OpenTofu"
  description  = "Used by GitHub Actions to apply OpenTofu changes"
  project      = var.project_id
}

# Grant project-level IAM roles to the service account
resource "google_project_iam_member" "sa_roles" {
  for_each = toset(var.sa_project_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Grant access to the tfstate GCS bucket
resource "google_storage_bucket_iam_member" "tfstate_object_admin" {
  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_storage_bucket_iam_member" "tfstate_legacy_bucket_reader" {
  bucket = "${var.project_id}-tfstate"
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.github_actions.email}"
}

