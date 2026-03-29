# PulseGrid AI
### Cloud Incident Intelligence and Failure Modeling Platform — HackUSF 2026

---

## What PulseGrid Is

PulseGrid AI is a scenario-aware incident intelligence system that transforms incident inputs into a structured dashboard for understanding failure propagation and guiding mitigation response.

It does one core job: take an incident signal, organizational weakness, or hypothetical failure scenario and produce a layered analysis that explains what is happening, what could happen next, and what should be done about it — across all seven causal layers simultaneously.

Most observability and monitoring tools alert when something has already broken. PulseGrid is built around a different premise: incidents don't emerge from nowhere. They propagate through a predictable chain of conditions — from upstream budget and structural decisions down through triggering events, internal amplification, telemetry signals, user degradation, and eventually organizational cost. PulseGrid reads the full chain.

This makes it useful in two modes:

**Live incident response** — Describe what you're seeing. PulseGrid maps the signals across the 7-layer Failure Propagation Chain, identifies the failure pattern, calculates blast radius, and generates a specific mitigation playbook with tool-level commands for now, next, and long-term prevention.

**Failure modeling and simulation** — Describe a structural weakness, an organizational constraint, or a what-if scenario. PulseGrid simulates what that failure would look like as it propagates, giving teams a way to stress-test decisions before they make it to production.

---

## The Failure Propagation Chain

PulseGrid's analytical framework maps every incident across seven causal layers. This is not the OSI model. These layers represent the human, organizational, architectural, and operational conditions that combine to produce infrastructure failures.

| Layer | Name | What it asks |
|-------|------|-------------|
| L0 | External Drivers | What upstream pressure existed before metrics moved? (budget cuts, understaffing, launch deadlines, regulatory changes) |
| L1 | Structural Conditions | What made the system architecturally fragile? (single points of failure, no failover, aggressive retry behavior) |
| L2 | Triggering Events | What event started the chain? (bad deploy, traffic spike, dependency failure, config error) |
| L3 | Internal Stress Mechanics | How did the system absorb and amplify the shock? (retry storms, queue overflow, connection pool exhaustion) |
| L4 | Telemetry Warning Signs | What quantitative signals are visible? (latency climbing, error rate rising, cache hit rate dropping) |
| L5 | User-Visible Degradation | What are users actually experiencing? (slow pages, errors, delayed notifications, regional splits) |
| L6 | Business / Mission Impact | What is the organizational consequence? (revenue loss, SLA breach, reputational harm, churn) |

The chain reads left to right: hidden causes → visible effects → organizational cost.

---

## What PulseGrid Is Not

PulseGrid is not just a chatbot. It is not a SIEM. It is not an observability dashboard. It is not anomaly detection. It is not a static scenario viewer.

It is closer to: incident reasoning, failure-chain modeling, blast-radius estimation, and response guidance — unified into a single interface.

---

## How It Works

### Three entry points, one unified experience

**Free-text input (primary):** The user describes what they're seeing — a symptom, a metric, a structural weakness, anything. PulseGrid extracts structured signals from natural language using a domain-specific keyword matrix, identifies the failure pattern, and begins building the analysis dashboard immediately. No questions required if the description contains enough signal.

**Guided wizard:** If the initial description doesn't contain sufficient signal for a full analysis, PulseGrid extracts whatever signals ARE present, pre-populates those question answers automatically, and asks only about the remaining gaps. If all five question dimensions are already covered by the description, the wizard is skipped entirely.

**Pre-built scenarios:** 13 hardcoded scenarios with pre-computed 20-step simulation timelines covering the most common infrastructure failure classes. Each scenario has a full chain analysis, blast radius propagation, and mitigation playbook.

### Live dashboard build

The analysis screen is a split panel. The left side handles Q&A and follow-up chat. The right side builds a live failure chain dashboard as signals are identified — not after all questions are answered, but immediately from the first description, updating with each additional answer. Judges and users see the chain being constructed in real time.

### Signal extraction

`_extract_signals_from_text()` in `chatbot.py` maps natural language to structured signal IDs using a keyword regex matrix covering:
- User impact signals: slow pages, timeouts, errors, regional splits, outage
- Telemetry signals: latency, error rate, retry rate, queue depth, CPU/cache
- Trigger signals: deploys, traffic spikes, dependency failures, DNS/service discovery, hardware
- Structural signals: single points of failure, no failover, aggressive retries, no circuit breaker
- External driver signals: cost cuts, understaffing, vendor constraints, regulatory changes

### Open-ended analysis

When an incident doesn't match any of the 13 known patterns at sufficient confidence, `open_ended_diagnose()` in `chatbot.py` uses GPT to generate a full 7-layer chain analysis from scratch. The prompt instructs the model to populate every layer with specific factors from the description and return structured JSON — identical format to the hardcoded scenario engine. This means PulseGrid can analyze any incident, not just the 13 pre-built ones.

### Blast radius propagation

`blast_radius.py` models a service dependency graph of 18 services across 6 tiers. When a failure is diagnosed, the engine propagates impact through the graph and estimates degradation percentages for each affected downstream service, showing which services are at direct risk versus second-hop risk.

---

## Architecture

```
pulsegrid/
├── api/
│   └── server.py          Pure stdlib HTTP server (no framework)
│                          Endpoints: /, /api/diagnose, /api/chat, /api/questions,
│                                     /api/extract, /api/state, /api/scenarios, /api/graph
├── engine/
│   ├── chain.py           7-layer failure chain definitions, QUESTIONS schema,
│                          scenario scoring matrix (13 pre-built patterns), diagnose()
│   ├── chatbot.py         Incident intelligence brain: diagnostic mode, scenario
│                          follow-up mode, signal extraction, open-ended GPT diagnosis,
│                          wizard signal pre-extraction
│   ├── blast_radius.py    Dependency graph propagation — how failures spread
│   ├── graph.py           Service topology (18 services across 6 tiers)
│   ├── recommendations.py Playbook generation per scenario and state
│   └── scoring.py         Per-service and system-level health scoring
├── simulator/
│   └── scenarios.py       13 pre-built scenario timelines (20-step each)
├── frontend/
│   └── index.html         Single-file frontend (CSS + HTML + JS, ~2400 lines)
└── run.py                 Entry point — starts the HTTP server
```

---

## Setup

### Requirements

- Python 3.9+
- No external packages required for core functionality (pure stdlib HTTP server)
- Optional: OpenAI API key for GPT-powered analysis (`OPENAI_API_KEY` env var)
- Optional: Override model with `PULSEGRID_CHAT_MODEL` (default: `gpt-4.1-mini`)

### Run

```bash
cd pulsegrid
python run.py
# → http://localhost:8000
```

### With OpenAI

```bash
export OPENAI_API_KEY=sk-...
cd pulsegrid
python run.py
```

Without an API key, the system uses deterministic fallback logic based on the signal matrix — no GPT narrative features, but full chain analysis and simulation still work.

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Serves `frontend/index.html` |
| GET | `/api/questions` | Returns question schema and layer definitions |
| GET | `/api/extract?message=...` | Extracts signals from free text; returns pre-answers and skippable questions |
| POST | `/api/diagnose` | Runs structured diagnosis from question responses |
| POST | `/api/chat` | AI chat in diagnostic or scenario mode; includes free-text bypass |
| GET | `/api/scenarios` | Lists all pre-built scenarios |
| GET | `/api/state?scenario=X&step=N` | Returns full simulation state at step N |
| GET | `/api/graph` | Service dependency graph nodes and edges |

---

## Key Design Decisions

**Why no framework?** Pure stdlib means zero install friction for evaluation. `python run.py` is the entire setup.

**Why 13 hardcoded scenarios?** They provide fast, consistent, demo-quality outputs for known incident classes. The open-ended GPT path covers any incident that doesn't match a template.

**Why live progressive dashboard instead of results at the end?** Showing the chain being built in real time as answers arrive communicates the analytical process directly. It's faster to understand and more compelling to evaluate than a blank screen followed by a results dump.

**Why not lock to scenario matching?** Real incidents are rarely clean archetypes. The GPT fallback ensures meaningful output for novel incident combinations rather than force-fitting the nearest template.

**Why split free-text and guided wizard?** Some users know exactly what's happening and want immediate analysis. Others need structure to articulate an incident. Both entry paths reach the same structured result.

---

## Benchmarks and Statistics

All numerical benchmarks shown in the UI are labeled as "Illustrative benchmark range" or "Scenario-aligned reference estimate" — derived from PagerDuty State of Digital Operations, Atlassian Incident Management report, Google SRE Book, CNCF Survey 2023, and scenario modeling. They are not claimed as precise measured operational values.

---

*Built for HackUSF 2026 by Dontavious Ellis*
