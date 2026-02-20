
# Google Secret Manager Accessor Service Account for GKE
resource "google_service_account" "external_secrets" {
  account_id   = "external-secrets-sa"
  display_name = "External Secrets Operator Service Account"
  project      = var.project_id
}

# Grant the service account access to Secret Manager
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.external_secrets.email}"
}

locals {
  wi_bindings = [
    "cloudflared/cloudflared-secret-accessor"
  ]
}

resource "google_service_account_iam_member" "workload_identity_binding" {
  for_each           = toset(local.wi_bindings)
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${each.value}]"
}
