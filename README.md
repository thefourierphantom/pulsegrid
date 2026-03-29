# PulseGrid AI
### Cloud Incident Reasoning and Failure Modeling Platform — HackUSF 2026

---

## What PulseGrid Is

PulseGrid AI is a scenario-aware incident reasoning and failure-modeling system for cloud infrastructure. It transforms incident inputs into a structured dashboard that helps teams understand failure propagation, estimate likely impact, and guide mitigation response.

Its core purpose is to take an incident signal, organizational weakness, or hypothetical failure scenario and produce a layered analysis of what is happening, what is likely to happen next, and what actions should be considered across all seven layers of the Failure Propagation Chain.

Most observability tools are designed to detect symptoms after something starts breaking. PulseGrid is built around a different premise: incidents are not isolated events. They emerge through chains of structural weakness, triggering conditions, amplification behavior, telemetry signals, user-facing degradation, and business consequences. PulseGrid helps teams reason across that chain.

This makes it useful in two modes:

1. **Live incident reasoning** — Describe what you are seeing. PulseGrid maps the signals across the seven-layer Failure Propagation Chain, infers a likely failure condition, estimates blast radius, and generates mitigation guidance for immediate response and longer-term resilience.

2. **Failure modeling and simulation** — Describe a structural weakness, organizational constraint, or what-if scenario. PulseGrid models how that failure could propagate, giving teams a way to stress-test decisions before they reach production.

---

## The Failure Propagation Chain

PulseGrid's analytical framework maps every incident across seven causal layers. This is not the OSI model. These layers represent the human, organizational, architectural, and operational conditions that combine to produce infrastructure failures.

| Layer | Name | What it asks |
|-------|------|-------------|
| L0 | External Drivers | What upstream pressure existed before metrics moved? Examples: budget cuts, understaffing, vendor constraints, launch deadlines, regulatory changes |
| L1 | Structural Conditions | What made the system fragile before the incident? Examples: single points of failure, weak failover design, dependency concentration, risky retry behavior |
| L2 | Triggering Events | What event started the chain? Examples: bad deploy, traffic spike, dependency failure, configuration error, resolver issue |
| L3 | Internal Stress Mechanics | How did the system absorb or amplify the shock? Examples: retry amplification, queue overflow, connection pool exhaustion, cascading timeouts |
| L4 | Telemetry Warning Signs | What quantitative signals became visible? Examples: latency climbing, error rate rising, queue depth growing, cache hit rate dropping |
| L5 | User-Visible Degradation | What were users actually experiencing? Examples: slow pages, failed requests, delayed notifications, regional inconsistency |
| L6 | Business / Mission Impact | What is the organizational consequence? Examples: revenue loss, SLA risk, reputational harm, customer churn, mission degradation |

The chain moves from hidden causes to visible effects to organizational cost.

---

## What PulseGrid Is Not

PulseGrid is not just a chatbot. It is not a SIEM. It is not a traditional observability dashboard. It is not pure anomaly detection. It is not just a static scenario viewer.

It is closer to a unified interface for:
- incident reasoning
- failure-chain modeling
- blast-radius estimation
- mitigation guidance
- scenario simulation

---

## How It Works

### Three entry points, one unified experience

**Free-text input (primary):**  
The user describes what they are seeing — a symptom, metric pattern, structural weakness, or hypothetical condition. PulseGrid extracts structured signals from natural language, synthesizes likely failure conditions, and begins building the analysis dashboard immediately. If the description contains enough signal, no additional questions are required.

**Guided wizard:**  
If the initial description does not contain sufficient signal for a complete analysis, PulseGrid pre-populates whatever it can infer and asks only about the remaining gaps. If all major dimensions are already covered by the description, the wizard can be skipped.

**Pre-built scenarios:**  
PulseGrid includes 13 pre-built scenarios with simulation timelines covering common infrastructure failure classes. These provide fast, consistent demo outputs for known failure patterns while still using the same seven-layer analytical framework.

### Live dashboard build

The analysis screen is a split panel. The left side handles Q&A and follow-up interaction. The right side builds a live failure-chain dashboard as signals are identified — not after all questions are answered, but progressively from the initial description and each follow-up input.

This allows users and judges to watch the chain form in real time instead of waiting for a final result dump.

### Signal extraction

Signal extraction maps natural language to structured infrastructure-relevant evidence, including:
- user impact signals: slow pages, timeouts, errors, regional splits, outage
- telemetry signals: latency, error rate, retry rate, queue depth, CPU/cache behavior
- trigger signals: deploys, traffic spikes, dependency failures, DNS or service discovery issues, hardware instability
- structural signals: single points of failure, weak redundancy, aggressive retries, missing circuit breaking
- external-driver signals: cost cuts, understaffing, vendor constraints, regulatory pressure

### Open-ended analysis

When an incident does not strongly match a known scenario pattern, PulseGrid can use GPT-assisted analysis to generate a full seven-layer chain from scratch. The model is prompted to reason through the incident in structured form and return output aligned with the same analytical schema used by the rest of the product.

This allows PulseGrid to go beyond fixed templates and produce useful reasoning for more novel or mixed-condition incidents.

### Blast radius propagation

PulseGrid models a service dependency graph across multiple infrastructure tiers. When a failure is diagnosed, the engine propagates likely impact through that graph and estimates which downstream services are at direct risk versus second-order risk.

The result is not just a diagnosis of what appears broken now, but a forward-looking estimate of what may degrade next.

### Uploaded context and organizational awareness

PulseGrid can also incorporate uploaded documents such as remediation plans, organizational structure notes, architecture references, or operational context. These documents enrich the model's understanding of priorities, dependencies, and response posture.

They are intended to improve context, not override the actual incident evidence.

---

## Architecture

```text
pulsegrid/
├── api/
│   └── server.py          Pure stdlib HTTP server
│                          Endpoints: /, /api/diagnose, /api/chat, /api/questions,
│                                     /api/extract, /api/state, /api/scenarios, /api/graph
├── engine/
│   ├── chain.py           Failure-chain definitions, question schema,
│                          diagnosis and analysis logic
│   ├── chatbot.py         Incident reasoning flow, signal extraction,
│                          open-ended GPT analysis, wizard pre-extraction
│   ├── blast_radius.py    Dependency graph propagation
│   ├── graph.py           Service topology
│   ├── recommendations.py Mitigation guidance and response logic
│   └── scoring.py         Service and system-level scoring
├── simulator/
│   └── scenarios.py       Pre-built scenario timelines
├── frontend/
│   └── index.html         Single-file frontend
└── run.py                 Entry point — starts the HTTP server
```

---

## Setup

### Requirements

- Python 3.9+
- No external packages required for core functionality
- Optional: OpenAI API key for GPT-assisted analysis (`OPENAI_API_KEY`)
- Optional: Override model with `PULSEGRID_CHAT_MODEL` (default: `gpt-4.1-mini`)

### Run

```bash
cd pulsegrid
python run.py
# http://localhost:8000
```

### With OpenAI

```bash
export OPENAI_API_KEY=sk-...
cd pulsegrid
python run.py
```

Without an API key, the system still supports deterministic signal extraction, structured chain analysis, scenario simulation, and dashboard generation. GPT-enhanced open-ended reasoning is optional.

---

## API Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Serves `frontend/index.html` |
| GET | `/api/questions` | Returns question schema and layer definitions |
| GET | `/api/extract?message=...` | Extracts signals from free text; returns inferred answers and skippable questions |
| POST | `/api/diagnose` | Runs structured diagnosis from responses and inferred context |
| POST | `/api/chat` | AI-assisted chat in diagnostic or scenario mode |
| GET | `/api/scenarios` | Lists pre-built scenarios |
| GET | `/api/state?scenario=X&step=N` | Returns simulation state at step `N` |
| GET | `/api/graph` | Returns dependency graph nodes and edges |

---

## Key Design Decisions

**Why no framework?**  
Pure stdlib keeps setup friction low for evaluation and demo environments. `python run.py` is the full startup path.

**Why pre-built scenarios?**  
They provide fast, consistent, demo-quality outputs for common failure classes. Open-ended analysis supports cases that do not fit those templates cleanly.

**Why progressive dashboard build?**  
Showing the chain build in real time communicates the reasoning process more clearly than a blank screen followed by a full results dump.

**Why not rely only on scenario matching?**  
Real incidents are messy. A useful incident reasoning system should support known patterns without forcing every case into a rigid bucket.

**Why support both free-text and guided input?**  
Some users can describe an incident directly. Others need structure to articulate the problem. Both entry points should converge on the same analytical output.

**Why support uploaded documents?**  
Real incident reasoning improves when the system understands local context such as service priorities, remediation posture, and dependency assumptions.

---

## Benchmarks and Statistics

Any numerical benchmarks shown in the UI should be treated as illustrative benchmark ranges, scenario-aligned reference estimates, or modeled values unless explicitly sourced and validated within the product. They are intended to support interpretation, not to claim real measured production telemetry.

---

## Current Product Scope

PulseGrid is best understood today as an MVP / prototype for incident reasoning, scenario simulation, and failure-chain analysis.

It is strongest at:
- structuring infrastructure incidents into a coherent causal model
- visualizing likely propagation across layers
- surfacing likely blast radius and mitigation direction
- demonstrating how cloud failures can be reasoned about beyond isolated alerts

It should not be framed as a replacement for mature production observability, SIEM, or incident command tooling.

---

*Built for HackUSF 2026 by Dontavious Ellis & Ashwin Neti*
