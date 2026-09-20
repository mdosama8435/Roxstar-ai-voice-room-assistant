# RoxStar AI Voice Room Assistant - Backend Service

FastAPI-based API gateway and data contracts service for the RoxStar AI Voice Room Assistant.

## Overview
The backend service manages room metadata, participant configurations, security contracts, structured logging, and system health checks. In later phases, it issues signed LiveKit JWT authentication tokens and interfaces with the persistence layer.

## Endpoints (Phase 1)
- `GET /health`: Basic liveness probe returning `{"status": "ok", "service": "roxstar-backend"}`.
- `GET /api/v1/system/status`: Real system runtime status and provider configuration check.
- `GET /api/v1/rooms/info`: Capabilities contract specification.

## Local Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Tests
```bash
python -m pytest tests/ -v
```

### 3. Run Development Server
```bash
uvicorn app.main:app --reload --port 8000
```
