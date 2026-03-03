module "my_py_app_sql" {
  source = "../modules/cloud-sql-postgres"

  project_id = var.project_id
  region     = var.region

  instance_name = "sample-todo-app-pg"
  database_name = "my_py_app"
  database_user = "my_py_app_user"

  db_password_secret_id = "sample-todo-app-db-password"

  service_account_id          = "sample-todo-app-db-client"
  workload_identity_namespace = "default"
  workload_identity_ksa_name  = "sample-todo-app"
}
