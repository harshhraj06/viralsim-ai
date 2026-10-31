# ViralSim AI

An original virtual-audience simulation starter with a responsive product workspace and a FastAPI backend. This repository is independently implemented; it does not incorporate MiroFish source code.

## Current capability boundaries

- **Implemented:** local video upload with extension/size validation, SQLite persistence, optional `ffprobe` metadata extraction, heuristic timeline anchors, persona catalog, seeded background simulation jobs, persisted reports, cohort and engagement estimates, recommendation hypotheses, comparison endpoint, report Q&A grounded in stored report fields, and a separate endpoint for user-provided actual outcomes.
- **Explicitly not implemented:** authenticated multi-user tenancy, cloud object storage, production job queue, semantic multimodal analysis, frame extraction, transcription, LLM-powered agent reasoning, statistically calibrated confidence intervals, automatic calibration, or platform algorithm replication.
- The simulation is a **transparent heuristic prototype**, not a validated predictive model. Timestamps are provisional anchors, not detected scene boundaries. Never present the values as real analytics.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
# Optional: install ffmpeg/ffprobe for video metadata
uvicorn backend.main:app --reload --port 8000
```

Open http://127.0.0.1:8000. API docs: http://127.0.0.1:8000/docs. Data is stored in `data/` and excluded from git.

## API

- `POST /api/videos/upload` — multipart field `file`
- `POST /api/videos/{id}/analyze`
- `POST /api/videos/{id}/simulate` — JSON `SimConfig`
- `GET /api/runs/{id}` and `GET /api/runs/{id}/report`
- `GET /api/personas`, `GET /api/videos`, `GET /api/runs`
- `POST /api/runs/{id}/ask`
- `POST /api/compare` — `{"run_a":"...","run_b":"..."}`
- `POST /api/videos/{id}/actual-performance`
- `GET /api/health`

## Before production

Add authentication and per-user authorization, signed private object storage, malware/content scanning, content-type inspection, quotas and rate limiting, durable Celery/Redis or equivalent jobs, task cancellation/retry semantics, observability, retention/deletion controls, privacy disclosures, and test coverage. Configure and evaluate actual video understanding and LLM providers before claiming semantic analysis. Add calibration only from appropriately consented, representative real-world analytics and report uncertainty only when statistically justified.
