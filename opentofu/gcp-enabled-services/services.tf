resource "google_project_service" "services" {
  for_each = toset(var.enabled_services)

  project            = var.project_id
  service            = each.key
  disable_on_destroy = true

  disable_dependent_services = false
}