output "instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.this.name
}

output "instance_connection_name" {
  description = "Cloud SQL instance connection name used by Cloud SQL Proxy."
  value       = google_sql_database_instance.this.connection_name
}

output "instance_public_ip" {
  description = "Cloud SQL public IPv4 address."
  value       = google_sql_database_instance.this.public_ip_address
}

output "database_name" {
  description = "Database name."
  value       = google_sql_database.this.name
}

output "database_user" {
  description = "Database user."
  value       = google_sql_user.this.name
}

output "db_password_secret_id" {
  description = "Secret Manager secret ID containing the generated database password."
  value       = google_secret_manager_secret.db_password.secret_id
}

output "workload_identity_service_account_email" {
  description = "Google service account email for workload identity."
  value       = google_service_account.workload_identity.email
}
