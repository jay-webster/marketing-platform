# Specification: Marketing Content-as-Code Platform (MVP)

## 1. Goal
Provide a single-organization platform where marketing teams manage content via version control, with an AI agent to assist in distribution and interrogation. Each client deployment runs as an isolated Docker image — one installation per client, eliminating multitenancy overhead and giving clients full deployment flexibility.

## 2. Core Architecture
- **Deployment Model:** Per-client Docker image. Each client gets their own isolated container and database. Clients can self-host or have the platform operator host on their behalf.
- **Backend:** Python-based, utilizing FastAPI for the interface.
- **Database:** Postgres, single-organization (no RLS, no tenant scoping required).

## 3. MVP Features
- **Admin Setup:** Initial administrator registration to bootstrap the installation.
- **Content Sync:** A version control integration (GitHub/Git) to pull content into the platform.
- **Agent Interrogation:** A conversational interface to query and generate from the organization's approved content library.

## 4. Security
- All endpoints that access application data must require an authenticated session.
- No PII (Personally Identifiable Information) shall be stored in plaintext.