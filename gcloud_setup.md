# Setup Initial GCP Infrastructure

## Prerequisites
1. Set the following environment variables
```sh
export GOOGLE_PROJECT="your-gcp-project-id"
export SERVICE_ACCOUNT_NAME="github-actions-tofu"
export WORKLOAD_IDENTITY_POOL="github"
export WORKLOAD_IDENTITY_PROVIDER="github"
export GITHUB_ORG="your-github-org"
export GITHUB_REPO="your-repo-name"
export LOCATION="global"
```

2. Install gcloud CLI, authenticate and create project
```sh
gcloud auth login
gcloud projects create $GOOGLE_PROJECT
gcloud config set project $GOOGLE_PROJECT
```

3. ~~Make sure the necessary APIs are enabled~~ Manage this through terraform.
```sh
gcloud services enable cloudresourcemanager.googleapis.com
gcloud services enable container.googleapis.com
gcloud services enable compute.googleapis.com
gcloud services enable iam.googleapis.com
gcloud services enable iamcredentials.googleapis.com
gcloud services enable sts.googleapis.com
gcloud services enable secretmanager.googleapis.com

gcloud services list
```

4. Grant roles to manage GKE (``roles/container.admin``, ``roles/compute.networkAdmin``, ``roles/iam.serviceAccountUser``). Maybe these roles should not be given to individual users but rather managed through Workload Identity Federation and Service Accounts? IDK You might still need these eventually when things break...
```sh
EMAIL=<your.email@example.com>

gcloud projects add-iam-policy-binding $GOOGLE_PROJECT --member="user:$EMAIL" --role=roles/container.admin
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT --member="user:$EMAIL" --role=roles/compute.networkAdmin
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT --member="user:$EMAIL" --role=roles/storage.objectAdmin
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT --member="user:$EMAIL" --role=roles/iam.serviceAccountUser
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT --member="user:$EMAIL" --role=roles/iam.workloadIdentityPoolAdmin
```

## Setting Up Workload Identity Federation Between GitHub Actions and GCP

1. Create service account
```sh
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
  --project=${GOOGLE_PROJECT} \
  --description="Used by GitHub Actions to apply OpenTofu changes" \
  --display-name="GitHub Actions OpenTofu"
```

2. Grant IAM Roles to the Service Account
```sh
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${GOOGLE_PROJECT}.iam.gserviceaccount.com"

# Kubernetes Engine Admin – create/manage GKE clusters
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/container.admin"  

# Compute Network Admin – create/manage VPC and subnets
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/compute.networkAdmin"

# Service Account User – needed for GKE node SA binding
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountUser"

# Service Usage Admin – enable/disable GCP APIs via Terraform
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/serviceusage.serviceUsageAdmin"

# Service Account Admin - manage service accounts and IAM policy bindings
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/iam.serviceAccountAdmin"

# Project IAM Admin - allow creating project-level IAM policy bindings
gcloud projects add-iam-policy-binding $GOOGLE_PROJECT \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/resourcemanager.projectIamAdmin"
```

3. Create a Workload Identity Pool
```sh
gcloud iam workload-identity-pools create ${WORKLOAD_IDENTITY_POOL} \
  --project=${GOOGLE_PROJECT} \
  --location=${LOCATION} \
  --display-name="GitHub Actions Pool"
```

4. Create Workload Identity Provider
```sh
gcloud iam workload-identity-pools providers create-oidc ${WORKLOAD_IDENTITY_PROVIDER} \
  --project=${GOOGLE_PROJECT} \
  --location=${LOCATION} \
  --workload-identity-pool=${WORKLOAD_IDENTITY_POOL} \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-condition="assertion.repository == '${GITHUB_ORG}/${GITHUB_REPO}'"
```

5. Allow the Service Account to be impersonated via Workflow Identity Federation through the specified repository
```sh
PROJECT_NUMBER=$(gcloud projects describe $GOOGLE_PROJECT --format="value(projectNumber)")

gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --project=${GOOGLE_PROJECT} \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/${LOCATION}/workloadIdentityPools/${WORKLOAD_IDENTITY_POOL}/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}"
```

6. Get the GCP_WORKLOAD_IDENTITY_PROVIDER_VALUE
```sh
gcloud iam workload-identity-pools providers describe "${WORKLOAD_IDENTITY_PROVIDER}" \
  --location="global" \
  --workload-identity-pool="${WORKLOAD_IDENTITY_POOL}" \
  --format="value(name)"
```

## Create Google Cloud Storage Bucket for terraform backend

1. Create storage bucket
```sh
BUCKET="$GOOGLE_PROJECT-tfstate"
LOCATION="europe-north2"

gcloud storage buckets create "gs://$BUCKET" \
  --location="$LOCATION" \
  --uniform-bucket-level-access

gcloud storage buckets update "gs://$BUCKET" --versioning
```

2. Add IAM policy for the GitHub Actions service account
```sh
# Storage Admin on the state bucket – read/write tfstate
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin"

# Probably not needed if storage admin is added
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.legacyBucketReader"
```

---

## Misc

**See IAM policies**
```sh
gcloud projects get-iam-policy $GOOGLE_PROJECT

gcloud iam service-accounts get-iam-policy $SA_EMAIL \
  --project=${GOOGLE_PROJECT}

gcloud storage buckets get-iam-policy gs://$BUCKET
```

**Get credentials**
```sh
gcloud container clusters get-credentials "${GOOGLE_PROJECT}-gke" --region $LOCATION --project $GOOGLE_PROJECT
```
