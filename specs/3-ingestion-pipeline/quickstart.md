# Quickstart: Epic 3 — Ingestion & Markdown Pipeline

**Branch**: `3-ingestion-pipeline`
**Generated**: 2026-03-13

---

## Prerequisites

- Epic 1 (IAM) complete and passing
- Epic 2 (GitHub Bridge) complete and passing
- Docker Compose running (Postgres on 5432)
- GCS bucket created (see below)

---

## Environment Variables

Add to `marketing-platform/.env` (and `.env.example`):

```dotenv
# GCS — Ingestion file storage
GCS_BUCKET_NAME=your-ingestion-bucket-name

# Optional tuning
WORKER_CONCURRENCY=5

# Local dev only — not used on GKE (Workload Identity used instead)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your-sa-key.json
```

---

## GCS Setup (Local Dev)

```bash
# 1. Create a bucket
gcloud storage buckets create gs://YOUR_BUCKET_NAME \
  --location=us-central1 \
  --uniform-bucket-level-access

# 2. Create a service account for local dev
gcloud iam service-accounts create ingestion-dev \
  --display-name="Ingestion Dev SA"

# 3. Grant objectAdmin on the bucket
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET_NAME \
  --member="serviceAccount:ingestion-dev@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 4. Download key (local dev only — never commit this file)
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=ingestion-dev@PROJECT_ID.iam.gserviceaccount.com

# 5. Set env var
export GOOGLE_APPLICATION_CREDENTIALS=$(pwd)/sa-key.json
```

---

## Install New Dependencies

```bash
cd marketing-platform
pip install pymupdf>=1.24.0 python-docx>=1.1.0 python-pptx>=1.0.0 google-cloud-storage>=2.10.0
# Or: pip install -r requirements.txt
```

---

## Run Migration

```bash
cd marketing-platform
alembic upgrade head
```

Applies migration `004_create_ingestion_tables.py` which creates: `ingestion_batches`, `ingestion_documents`, `processed_documents`.

---

## Start the Server

```bash
cd marketing-platform
uvicorn src.main:app --reload --port 8080
```

The queue worker pool starts automatically via `lifespan`. On startup you will see:
```
INFO: Started 5 queue workers + timeout watchdog
```

---

## Smoke Test — Submit a Batch

```bash
# 1. Get a JWT (assumes admin user exists from Epic 1)
TOKEN=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"YourPassword1!"}' \
  | jq -r '.data.access_token')

# 2. Submit a batch with two test files
curl -X POST http://localhost:8080/api/v1/ingestion/batches \
  -H "Authorization: Bearer $TOKEN" \
  -F "folder_name=Test Folder" \
  -F "files=@/path/to/test.docx" \
  -F "files=@/path/to/test.pdf"

# 3. Poll batch status (replace BATCH_ID)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/ingestion/batches/BATCH_ID

# 4. Preview a completed document (replace DOC_ID)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/ingestion/batches/BATCH_ID/documents/DOC_ID/preview

# 5. Export completed documents as ZIP
curl -H "Authorization: Bearer $TOKEN" \
  -X POST http://localhost:8080/api/v1/ingestion/batches/BATCH_ID/export \
  -H "Content-Type: application/json" \
  -d '{"document_ids":[]}' \
  --output batch_export.zip
```

---

## Run Tests

```bash
cd marketing-platform
pytest tests/api/test_ingestion.py tests/utils/test_extractors.py tests/utils/test_pipeline.py -v
```

---

## New Source Files (Epic 3)

```
marketing-platform/
├── src/
│   ├── api/
│   │   └── ingestion.py          ← New: 7 endpoints
│   └── models/
│       ├── ingestion_batch.py    ← New
│       ├── ingestion_document.py ← New
│       └── processed_document.py ← New
├── utils/
│   ├── gcs.py                    ← New: GCS upload/download/delete
│   ├── extractors.py             ← New: per-format text extraction
│   ├── ingestion_pipeline.py     ← New: Claude structuring (two-call)
│   └── queue.py                  ← New: worker pool + watchdog
├── migrations/versions/
│   └── 004_create_ingestion_tables.py  ← New
└── tests/
    ├── api/
    │   └── test_ingestion.py     ← New
    └── utils/
        ├── test_extractors.py    ← New
        └── test_pipeline.py      ← New
```

---

## GKE Workload Identity Setup (Production)

```bash
# 1. Create GCP Service Account
gcloud iam service-accounts create marketing-platform-sa \
  --display-name="Marketing Platform SA"

# 2. Grant GCS permissions
gcloud storage buckets add-iam-policy-binding gs://YOUR_BUCKET \
  --member="serviceAccount:marketing-platform-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 3. Enable Workload Identity binding
gcloud iam service-accounts add-iam-policy-binding \
  marketing-platform-sa@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:PROJECT_ID.svc.id.goog[default/marketing-platform-ksa]"

# 4. Annotate the Kubernetes Service Account (see infra/k8s/base/)
kubectl annotate serviceaccount marketing-platform-ksa \
  iam.gke.io/gcp-service-account=marketing-platform-sa@PROJECT_ID.iam.gserviceaccount.com
```

`GOOGLE_APPLICATION_CREDENTIALS` is **not set** in the K8s deployment — ADC resolves via Workload Identity automatically.
