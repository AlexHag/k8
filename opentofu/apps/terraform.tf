terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.28.0"
    }
    random = {
      source = "hashicorp/random"
    }
  }

  backend "gcs" {
    bucket = "${var.project_id}-tfstate"
    prefix = "terraform/state/apps"
  }

  required_version = ">= 1.9.0"
}

provider "google" {
  project = var.project_id
  region  = var.region
}
