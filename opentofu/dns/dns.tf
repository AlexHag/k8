# Static external IP for Envoy Gateway LB
resource "google_compute_address" "envoy_gateway_lb" {
  name   = "${var.project_id}-envoy-gateway-lb-ip"
  region = var.region
}

resource "google_dns_managed_zone" "main" {
  name     = "gke-dns-zone"
  dns_name = var.fully_qualified_domain_name
}

resource "google_dns_record_set" "argocd" {
  name         = "argocd.${var.fully_qualified_domain_name}"
  type         = "A"
  ttl          = 300
  managed_zone = google_dns_managed_zone.main.name
  rrdatas      = [google_compute_address.envoy_gateway_lb.address]
}

resource "google_dns_record_set" "app" {
  name         = "app.${var.fully_qualified_domain_name}"
  type         = "A"
  ttl          = 300
  managed_zone = google_dns_managed_zone.main.name
  rrdatas      = [google_compute_address.envoy_gateway_lb.address]
}

resource "google_dns_record_set" "sample-todo-app" {
  name         = "sample-todo-app.${var.fully_qualified_domain_name}"
  type         = "A"
  ttl          = 300
  managed_zone = google_dns_managed_zone.main.name
  rrdatas      = [google_compute_address.envoy_gateway_lb.address]
}

resource "google_dns_record_set" "openclaw" {
  name         = "openclaw.${var.fully_qualified_domain_name}"
  type         = "A"
  ttl          = 300
  managed_zone = google_dns_managed_zone.main.name
  rrdatas      = [google_compute_address.envoy_gateway_lb.address]
}
