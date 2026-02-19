terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.28.0"
    }
  }

  backend "gcs" {
    bucket = "${var.project_id}-tfstate"
    prefix = "terraform/state/gke"
  }

  required_version = ">= 1.9.0"
}

provider "google" {
  project = var.project_id
  region  = var.region
}
