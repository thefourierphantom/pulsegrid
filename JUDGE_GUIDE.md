# PulseGrid — Judge's Guide
### HackUSF 2026 | Cloud Resilience & Vulnerability Intelligence Platform

---

## The Core Problem

Cloud infrastructure fails. But it rarely fails without warning — and those warnings almost never start in the software.

They start in the physical world.

A hurricane approaches a data center cluster. A power utility issues a brownout notice. A government announces a data sovereignty regulation. A cloud provider runs out of hardware in a region because AI demand consumed all available compute. A vendor is sanctioned overnight.

**Every one of these real-world events creates conditions that eventually show up in your telemetry — but only after it's already too late to act cheaply.**

Traditional monitoring tools (Datadog, CloudWatch, Grafana) watch what is happening in your metrics. PulseGrid watches what is *about to happen* — and contextualizes why, using a layer of world-level intelligence that conventional monitoring ignores entirely.

---

## Why Hardware Constraints Matter

Software does not exist in isolation. **Every process runs on physical hardware. Every byte moves through a physical wire. Every service depends on power, cooling, and connectivity that exists in the real world.**

Cloud infrastructure is not magic — it is:
- Server racks in buildings that flood, burn, and lose power
- Fiber cables under oceans that get cut by ships and earthquakes
- Power grids that brownout during heat waves
- Hardware that is backordered for 16 weeks because semiconductor fabs are capacity-constrained
- Vendors that get sanctioned by governments overnight

When operators think about "cloud reliability," they often stop at the software layer: circuit breakers, retries, autoscaling. PulseGrid forces the conversation one layer deeper — into the physical, economic, and geopolitical conditions that determine whether your infrastructure will hold up.

---

## How PulseGrid Works

PulseGrid operates across three layers of intelligence:

### Layer 1 — Root Cause Intelligence (Pre-Signal)
Before any metric moves, PulseGrid surfaces the world-level conditions that create risk. These are the factors that determine **why** a system might degrade before the latency even starts climbing:

| Domain | Examples |
|--------|----------|
| Physical Infrastructure | Hurricane approaching datacenter, cooling unit failures, seismic risk zones |
| Power & Energy | Grid brownouts, generator fuel reserves, power contract renewals |
| Network & Connectivity | BGP routing anomalies, fiber route status, peering point health |
| Economic Pressure | Vendor capacity constraints, cost-cutting decisions, contract expirations |
| Geopolitical & Regulatory | Sanctions, data sovereignty laws, export controls on hardware |

### Layer 2 — Telemetry Signal Detection
PulseGrid monitors 8 real-time signal categories across every service in the dependency graph:

| Signal | What it means |
|--------|---------------|
| **Latency Drift** | p95/p99 response time rising before errors appear |
| **Error Creep** | Persistent low-level error rate growth — not noise |
| **Retry Amplification** | Services retrying aggressively, multiplying downstream load |
| **Timeout Clustering** | Multiple services timing out against the same dependency |
| **Resource Pressure** | CPU saturation, connection pool exhaustion, queue depth growth |
| **Cache Collapse** | Hit rate falling → backend pressure increasing |
| **Queue Depth Growth** | Backlog forming faster than workers can drain |
| **Regional Divergence** | One zone behaving differently from peers |

These signals are individually weak. PulseGrid's scoring engine finds **when they move together** — which is when real risk exists.

### Layer 3 — Blast Radius Forecasting
Using a directed service dependency graph, PulseGrid propagates risk from degrading services to the services that depend on them. This answers the question most monitoring tools cannot: **"Which services will be affected next, and how severely?"**

The propagation algorithm:
1. Score each service individually based on its own telemetry signals
2. For each dependency edge (A depends on B), if B's score exceeds a threshold, A's score is elevated proportionally to the edge weight
3. Repeat for 2 hops through the graph
4. Rank all services by propagated risk score

This produces a **blast radius forecast** — a ranked list of what breaks next — before the cascade reaches those services.

---

## The Service Graph

PulseGrid models a representative cloud-native service topology with 7 nodes:

```
                    Frontend
                        │
                   API Gateway
                   /    │    \
                Auth  Cache  Queue
                              │
                           Worker
                           /
                       Database
```

Each directed edge represents a dependency with a propagation weight (0–1). Higher weight = more risk transfers when the dependency degrades.

| Edge | Weight | Meaning |
|------|--------|---------|
| Frontend → API Gateway | 0.95 | Frontend is almost entirely dependent on API |
| API Gateway → Auth | 0.85 | Every request must authenticate |
| API Gateway → Cache | 0.70 | Most reads go through cache |
| Queue → Worker | 0.90 | Workers drain queue — tight coupling |
| Worker → Database | 0.85 | Workers persist to database |

---

## Risk Scoring

Each service is scored 0.0–1.0 using a weighted composite of its normalized telemetry signals:

```
risk_score = 0.28 × latency_drift
           + 0.25 × error_creep
           + 0.20 × retry_amplification
           + 0.15 × timeout_clustering
           + 0.12 × resource_pressure
```

**Multi-signal amplification:** When 3+ signals are elevated simultaneously, the score is amplified by 20–35%. Correlated stress is more dangerous than isolated stress.

**State thresholds:**

| Score Range | State | Color |
|-------------|-------|-------|
| 0.00–0.25 | Healthy | 🟢 Green |
| 0.25–0.45 | Watch | 🟡 Yellow |
| 0.45–0.65 | Unstable | 🟠 Orange |
| 0.65–0.80 | Vulnerable | 🔴 Red |
| 0.80–1.00 | Cascading | 🟣 Purple |

---

## Scenario Library (13 Scenarios, 6 Categories)

### Baseline
| Scenario | Description |
|----------|-------------|
| Healthy Baseline | All systems nominal — shows the clean state before any degradation |

### Natural Disaster & Environmental
| Scenario | Root Cause | Key Signals |
|----------|-----------|-------------|
| Hurricane: Datacenter Region | Cat 3 hurricane → thermal stress, power instability, coastal fiber damage | CPU throttling → latency → timeouts → errors |
| Power Grid Brownout | Regional voltage reduction → CPU frequency scaling | Uniform latency rise across all services |
| Seismic Zone Failure | 6.2M earthquake → sudden datacenter power loss | Step-change failure, no graceful shutdown |

### Infrastructure & Network
| Scenario | Root Cause | Key Signals |
|----------|-----------|-------------|
| BGP Route Leak | Misconfigured BGP peer misdirects global traffic | Latency spike → timeout clustering → partial recovery |
| DNS Resolver Degradation | DNS resolver fails → lookup timeouts | Timeout clustering before error rate climbs |

### Cascade Failure Patterns
| Scenario | Root Cause | Key Signals |
|----------|-----------|-------------|
| Retry Storm | Auth service fails → aggressive client retries → API gateway overloads | Error → retry amplification → connection saturation |
| Queue Backlog | Workers can't keep up → queue depth builds → cascading latency | Queue depth → worker CPU → database load |
| Regional Divergence | One zone's workers fail → intermittent errors → replication lag | Error creep + latency drift in one zone |

### Geopolitical & Regulatory
| Scenario | Root Cause | Key Signals |
|----------|-----------|-------------|
| Regulatory Forced Reroute | EU data sovereignty law → traffic must take longer paths | Sustained latency increase, no hard failure — SLO erosion |
| CDN Provider Sanctioned | OFAC sanctions → emergency failover to 2× latency secondary CDN | Spike during cutover → sustained degradation |

### Economic Pressure
| Scenario | Root Cause | Key Signals |
|----------|-----------|-------------|
| Vendor Capacity Crunch | Cloud region capacity exhausted by AI demand → autoscaling blocked | Resource pressure → queue build → cascade |
| Cost-Cut Redundancy Loss | Redundant cache nodes removed to cut spend → single point of failure | Sudden step-change failure after a healthy period |

---

## Reading the Dashboard

### Header
- **Active scenario name and category** — always visible
- **Playback controls** — step through time manually or auto-play
- **System State Badge** — overall risk state and composite score

### Left Sidebar — Scenario Library
- Organized by category (6 categories, 13 scenarios)
- Click any scenario to load it
- **Root Cause Intelligence panel** (bottom of sidebar): shows the world-level factors that explain *why* this scenario is happening — before the metrics move

### Center — EKG Timeline (top)
- System composite health line (bright blue) over 32 time steps
- Per-service lines (muted, colored by tier)
- State zone bands: green/yellow/orange/red/purple regions
- Transition dots: colored dots at each state change event
- Current step cursor: vertical line + dot at the active time step

### Center — Service Dependency Graph (bottom)
- 7 service nodes, each with a risk arc showing current score
- Arc fill and color reflect propagated risk score (after graph propagation)
- Edges are color-coded by the stress level of adjacent services
- Hover over any node for full telemetry breakdown

### Right Panel
- **System Risk State**: large score + state label + 5 signal evidence bars
- **Service Risk Scores**: all 7 services ranked by propagated risk
- **Blast Radius Forecast**: propagated risk ranking — which services are next
- **Recommended Actions**: immediate actions + optimization opportunities, matched to the active failure pattern

---

## Demo Script (3–4 minutes)

**Step 1 — Establish baseline** (~30 sec)
Select "Healthy Baseline." Hit Play. Show the EKG flat, all services green, blast radius clear. Explain the graph topology. This is what "normal" looks like.

**Step 2 — Retry Storm** (~60 sec)
Select "Retry Storm." Hit Play. Walk through:
- Auth service degrades first (error creep, retry amplification)
- API Gateway follows (retry amplification → connection saturation)
- Blast radius forecasts Frontend as next at risk — *before* Frontend metrics move
- Recommendations fire: circuit breaker, exponential backoff
- Context panel shows the software-level root cause (no circuit breaker configured, fixed retry interval)

**Step 3 — Hurricane Datacenter** (~60 sec)
Select "Hurricane: Datacenter Region." Walk through the Root Cause Intelligence panel *first*: "A Category 3 hurricane is 80 miles from the datacenter. Cooling is stressed. Power is fluctuating. This is happening before any metric moves." Then hit Play and show how the physical world eventually shows up in telemetry: CPU throttling first, then latency, then errors.

**Step 4 — Vendor Capacity Crunch** (~30 sec)
Select "Vendor Capacity Crunch." Explain the context: AI demand consumed cloud region capacity. Show how an economic constraint — a provider running out of hardware — eventually translates into service degradation without any software bug. This is the "software is bounded by hardware" story.

**Closing statement:**
"Datadog tells you what is failing. PulseGrid tells you what is about to fail, which services will be impacted next, and — critically — why it's happening at the physical and geopolitical layer before your metrics even notice. That's the gap we're filling."

---

## Technical Architecture

```
pulsegrid/
├── run.py                      Single entry point
├── engine/
│   ├── graph.py                7-node service dependency graph (directed, weighted)
│   ├── scoring.py              Weighted composite risk scoring + state machine
│   ├── blast_radius.py         Graph propagation engine (2-hop, threshold-based)
│   └── recommendations.py      7 rule-based recommendation patterns
├── simulator/
│   └── scenarios.py            13 scenarios with sigmoid degradation curves + context intelligence
├── api/
│   └── server.py               Pure stdlib HTTP server (no external frameworks)
└── frontend/
    └── index.html              Single-file SPA (EKG canvas, SVG graph, Intel panel)
```

**Zero external dependencies.** Runs with Python 3.8+ stdlib + numpy + pandas (pre-installed on any data science machine). No pip install required.

**Start:** `cd pulsegrid && python3 run.py` → open http://localhost:8765

---

## Key Technical Differentiators

| Feature | PulseGrid | Datadog/CloudWatch |
|---------|-----------|-------------------|
| Pre-signal root cause intelligence | ✅ Physical, economic, geopolitical | ❌ Metrics only |
| Blast radius forecasting | ✅ Graph propagation (2-hop) | ❌ Threshold alerting only |
| Dependency-aware risk scoring | ✅ Propagated scores through graph | ❌ Per-metric thresholds |
| Multi-signal correlation | ✅ Correlated stress amplification | ❌ Independent alert rules |
| World-layer context | ✅ Hurricane, sanctions, capacity | ❌ No world context |
| Recommended actions per failure pattern | ✅ 7 matched rule patterns | ⚠️ Generic runbooks |

---

*PulseGrid — HackUSF 2026. Built in one weekend.*
