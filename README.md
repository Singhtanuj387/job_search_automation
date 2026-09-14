---
title: Job Search Automation
emoji: 💼
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: 5.16.0
app_file: app.py
pinned: false
---

# Job Search Automation Engine (Phase 1)

Modular, resilient job-listing acquisition engine designed for high-confidence job discovery, deduplication, and blocking diagnostics.

## Features

- **Multi-Source Acquisition**: Unified adapter interface across Tier A and Tier B sources:
  - **Arbeitnow**: Official public Job Board API
  - **Greenhouse ATS**: Public board endpoints for top tech companies (Canonical, Stripe, GitLab, Figma, Airbnb, Reddit, etc.)
  - **Lever ATS**: Public postings API for companies (Spotify, Benchling, Palantir, Deliveroo, etc.)
  - **Remotive**: Official remote jobs API with salary & location tags
  - **Jobicy**: Remote tech jobs feed with seniority and compensation ranges
  - **Career Pages JSON-LD**: Structured schema.org/JobPosting extractor
- **Politeness & Anti-Blocking Layer**:
  - Per-domain rate limiting with jitter (`uniform(0.8, 1.4)`)
  - Complies with `Crawl-delay` declared in `robots.txt`
  - Optional proxy routing (via `--proxy` or `HTTP_PROXY`) with direct egress fallback
- **Accurate Block Detection**:
  - Distinguishes 200 OK with CAPTCHA/challenge walls (Cloudflare Turnstile, "Just a moment...", hCaptcha, reCAPTCHA, PerimeterX, AWS WAF) from legitimate listings.
  - Halts further domain hits on block detection; **zero CAPTCHA solving or credential automation**.
- **Fuzzy Deduplication**:
  - `(company, title, location)` fuzzy clustering with legal suffix removal and city normalization.
  - Automatically merges cross-platform reposts, retaining the highest-confidence posting.
- **Resumable Run Engine**:
  - SQLite-backed state and task queue (`data/jobs.db`). Runs can resume with `--resume`.
- **Structured Logging**:
  - JSON Lines log stream (`logs/engine_YYYYMMDD.jsonl`) and formatted console output.

## Installation

```bash
cd /mnt/extra/morningstar/Gradebuddy/job_search_automation
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Running Searches

```bash
## Phase 2 Web Application

The project includes a complete claude.ai-style web application wrapping the acquisition engine:
- Natural-language chat interface
- PDF/DOCX resume upload and text extraction
- Onboarding flow (role, location, seniority)
- LLM tailoring: tailored resume bullets and draft cover letters
- Qualitative fit framing (**no raw ATS score surfaced**)
- Encrypted API key storage (Anthropic Claude, Google Gemini, OpenAI, AWS Bedrock)
- Automated nightly scheduler with morning report waiting in chat
- Application Tracker Kanban pipeline & strict privacy-scoped Gmail search query preview

### Running the Web Application

```bash
# Start backend server (serves both FastAPI API and compiled React frontend)
.venv/bin/uvicorn web.backend.app:app --host 127.0.0.1 --port 8000
```
Open **`http://127.0.0.1:8000/`** in your browser.

### Running Frontend with Hot-Reload (Dev Mode)

```bash
cd web/frontend
npm run dev
```
```

## Running Tests

```bash
.venv/bin/pytest tests/ -v
```

## Project Layout

```
job_search_automation/
├── .venv/                         # Isolated Python virtual environment
├── requirements.txt               # Locked dependencies
├── run_search.py                  # CLI entrypoint
├── core/
│   ├── models.py                  # Pydantic schema: NormalizedJob, RawResult, QueryConfig
│   ├── adapter_base.py            # BaseAdapter ABC: fetch(), parse(), health_check()
│   ├── politeness.py              # DomainRateLimiter with jitter & robots.txt Crawl-delay
│   ├── block_detector.py          # Anti-bot and challenge detector
│   ├── dedup.py                   # Fuzzy deduplication engine
│   ├── storage.py                 # SQLite task queue & run persistence
│   ├── logger.py                  # Structured JSON Lines logger
│   └── orchestrator.py            # Main multi-source orchestrator
├── adapters/
│   ├── arbeitnow.py               # Tier A Arbeitnow API adapter
│   ├── greenhouse.py              # Tier A Greenhouse ATS adapter
│   ├── lever.py                   # Tier A Lever ATS adapter
│   ├── remotive.py                # Tier A Remotive API adapter
│   ├── jobicy.py                  # Tier A Jobicy API adapter
│   └── career_page_jsonld.py      # Tier B schema.org/JobPosting extractor
├── data/
│   ├── jobs.db                    # SQLite run state database
├── results.json                   # Deduplicated normalized jobs output
├── run_report.json                # Per-source health and dedup report
└── tests/
    ├── test_models.py
    ├── test_block_detector.py
    ├── test_politeness.py
    ├── test_dedup.py
    ├── test_storage.py
    ├── test_adapters.py
    └── test_orchestrator.py
```
