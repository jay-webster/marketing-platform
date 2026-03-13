# Quickstart: Epic 1 — IAM Development Setup

## Prerequisites
- Docker + Docker Compose
- Python 3.13
- A running PostgreSQL instance (local Docker or `docker compose up local-postgres`)

## 1. Environment Setup

```bash
cd marketing-platform
cp .env.example .env
```

Minimum `.env` for local development:
```env
DATABASE_URL=postgresql+asyncpg://myuser:mypassword@localhost:5432/dev_db
SECRET_KEY=change-me-to-a-random-32-char-string-for-dev
INITIAL_ADMIN_TOKEN=local-setup-token
APP_URL=http://localhost:8000

# SMTP — use a local mail catcher like Mailpit for dev
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASS=
SMTP_FROM=noreply@localhost
```

## 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Run Database Migration

```bash
alembic upgrade head
```

## 4. Start the API

```bash
uvicorn src.main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

## 5. Bootstrap the First Admin

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -H "X-Setup-Token: local-setup-token" \
  -d '{"email":"admin@example.com","display_name":"Admin","password":"Str0ng!Pass1"}'
```

After this succeeds, **remove `INITIAL_ADMIN_TOKEN` from `.env`**. The endpoint will reject all future calls.

## 6. Login and Get an Access Token

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Str0ng!Pass1"}'
```

Use the returned `access_token` as `Authorization: Bearer <token>` on all subsequent calls.

## 7. Run Tests

```bash
pytest tests/ -v
```
