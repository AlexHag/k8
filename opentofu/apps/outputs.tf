output "my_py_app_cloudsql_connection_name" {
  description = "Cloud SQL connection name for sample-todo-app."
  value       = module.my_py_app_sql.instance_connection_name
}

output "my_py_app_workload_identity_service_account" {
  description = "Workload identity GSA email used by sample-todo-app."
  value       = module.my_py_app_sql.workload_identity_service_account_email
}

output "my_py_app_db_password_secret_id" {
  description = "Secret Manager secret ID containing sample-todo-app DB password."
  value       = module.my_py_app_sql.db_password_secret_id
}
