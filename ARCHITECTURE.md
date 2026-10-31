# Architecture notes

## Current execution path

```text
Browser workspace
  ├─ multipart upload ──> FastAPI validation (extension, size, container signature)
  │                        ├─ private local file under data/uploads/
  │                        ├─ optional ffprobe metadata
  │                        └─ SQLite video record
  ├─ analyze request ───> metadata + explicitly provisional timeline anchors
  └─ simulation request -> persisted queued run -> FastAPI background task
                           ├─ deterministic seed + persona priors
                           ├─ synthetic cohort estimates and reaction strings
                           ├─ heuristic recommendations with evidence limitations
                           └─ persisted report + status polling

Reports -> dashboard, cohort details, comparison endpoint, report-grounded Q&A
Actual outcomes -> separately stored user submissions; never auto-calibrated
```

## MiroFish concepts adapted at the design level

The implementation uses structured heterogeneous persona profiles, reproducible runs, cohort aggregation, report interaction, and an inspectable workflow. It does **not** copy MiroFish source code or bundle OASIS, Zep, GraphRAG, or its agent orchestration. The current run engine is a small deterministic heuristic rather than a full multi-agent simulation. That limitation is surfaced in the UI and report payload.

## Production evolution

1. Add user identity and ownership foreign keys, then enforce authorization for every video/run/report query.
2. Move files to private object storage with short-lived signed URLs, lifecycle policies, scanning and deletion workflows.
3. Move long-running jobs to Redis/Celery or a durable queue; use atomic state transitions, idempotency keys, retry limits and cancellation.
4. Add a provider interface for frame sampling, audio extraction, transcription, OCR, scene boundaries and multimodal interpretation. Store per-feature provenance and model versions.
5. Replace heuristics with a documented behavioral model and independent agent state. Give each agent a distinct profile, preferences and bounded per-run memory; use batched concurrency limits and deterministic seeds where supported.
6. Evaluate predictions against consented, representative real outcomes. Track calibration drift by platform, category and cohort. Only expose uncertainty intervals after a valid statistical method has been implemented.
7. Add automated tests, audit logs, quotas, rate limits, privacy/retention controls, metrics and structured logging.

## Important limitation

The current demo accepts a valid video-container signature but does not fully decode or semantically inspect the media. It does not claim detected scenes, transcript accuracy, actual human responses, platform algorithm fidelity or validated prediction accuracy.
