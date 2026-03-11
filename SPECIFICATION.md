# Specification: Marketing Content-as-Code Platform (MVP)

## 1. Goal
Provide a multitenant platform where marketing teams manage content via version control, with an AI agent to assist in distribution and interrogation.

## 2. Core Architecture
- **Multitenancy:** Single Postgres Database using Row-Level Security (RLS).
- **Isolation Logic:** Every session must set the `app.current_tenant_id` session variable before executing queries.
- **Backend:** Python-based, utilizing FastAPI for the interface.
- **Deployment:** Containerized (Docker) for GCP Cloud Run.

## 3. MVP Features
- **Tenant Onboarding:** A script to create a `tenant_id` and initialize their scoped schema access.
- **Content Sync:** A version control integration (GitHub/Git) to pull content into the platform.
- **Agent Interrogation:** A GPT-style interface to "Ask your data" (using your Snowflake-to-Postgres sync foundation).

## 4. Security
- RLS Policy must block any access where `tenant_id` does not match the session context.
- No PII (Personally Identifiable Information) shall be stored in plaintext.