# engine/chain.py
# PulseGrid AI — Failure Propagation Chain Engine
#
# Models the 7-layer failure chain from the Failure Propagation Chain framework:
#   Layer 0  External Drivers        (what broad forces created risk)
#   Layer 1  Structural Conditions   (what made the system fragile)
#   Layer 2  Triggering Events       (what actually started the chain)
#   Layer 3  Internal Stress Mechanics (how the system absorbed the shock)
#   Layer 4  Telemetry Warning Signs  (what the numbers show)
#   Layer 5  User-Visible Degradation (what users experience)
#   Layer 6  Business / Mission Impact (why it matters)
#
# The diagnostic engine maps user responses to scenario + chain analysis.
# Every output is traceable to a specific layer and a specific observed signal.

# ── Layer definitions ─────────────────────────────────────────────────────────

LAYERS = [
    {
        "id":          "external_drivers",
        "number":      0,
        "label":       "External Drivers",
        "question":    "What broad forces were creating risk before metrics moved?",
        "description": "Upstream pressures that created fragility before any incident began",
        "color":       "#6366f1",
        "examples":    ["Budget pressure", "Understaffed ops", "Launch pressure", "Regulatory change", "Vendor constraint"],
    },
    {
        "id":          "structural_conditions",
        "number":      1,
        "label":       "Structural Conditions",
        "question":    "What made the system architecturally fragile?",
        "description": "Design decisions that allowed the trigger to escalate",
        "color":       "#8b5cf6",
        "examples":    ["Single point of failure", "No failover", "Aggressive retries", "No circuit breaker"],
    },
    {
        "id":          "triggering_events",
        "number":      2,
        "label":       "Triggering Events",
        "question":    "What event actually started the chain?",
        "description": "The proximate cause — the thing that broke first",
        "color":       "#f59e0b",
        "examples":    ["Bad deploy", "Traffic spike", "Dependency slowdown", "Hardware failure", "Config error"],
    },
    {
        "id":          "stress_mechanics",
        "number":      3,
        "label":       "Internal Stress Mechanics",
        "question":    "How did the system absorb — and amplify — the shock?",
        "description": "The internal propagation patterns that turned a trigger into a cascade",
        "color":       "#ef4444",
        "examples":    ["Retry storms", "Queue overflow", "Connection exhaustion", "Cache collapse", "Thread saturation"],
    },
    {
        "id":          "telemetry_signals",
        "number":      4,
        "label":       "Telemetry Warning Signs",
        "question":    "What quantitative signals are you observing?",
        "description": "The measurable indicators in your monitoring tools",
        "color":       "#fb923c",
        "examples":    ["Latency climbing", "Error rate rising", "Timeouts increasing", "Cache hit rate dropping"],
    },
    {
        "id":          "user_degradation",
        "number":      5,
        "label":       "User-Visible Degradation",
        "question":    "What are users actually experiencing?",
        "description": "The customer-facing symptoms of the underlying failure",
        "color":       "#fbbf24",
        "examples":    ["Pages loading slowly", "Errors on checkout", "Notifications delayed", "One region worse"],
    },
    {
        "id":          "business_impact",
        "number":      6,
        "label":       "Business / Mission Impact",
        "question":    "What is the business or operational consequence?",
        "description": "The cost to the organization if the chain is not resolved",
        "color":       "#34d399",
        "examples":    ["Revenue loss", "SLA violation", "Reputational harm", "Compliance breach"],
    },
]

LAYER_BY_ID = {l["id"]: l for l in LAYERS}


# ── Diagnostic question flow ──────────────────────────────────────────────────
# Questions are organized to collect info at each layer, starting from Layer 5
# (what users see) and working up to Layer 0 (root causes).

QUESTIONS = [
    {
        "id":    "q_user_impact",
        "layer": "user_degradation",
        "text":  "What are users currently experiencing?",
        "type":  "multi",
        "options": [
            {"id": "slow_pages",      "label": "Pages or API responses loading slowly",           "weight": {"latency": 2}},
            {"id": "errors",          "label": "Errors or failed requests",                        "weight": {"errors": 2}},
            {"id": "timeouts",        "label": "Requests timing out entirely",                     "weight": {"timeouts": 2}},
            {"id": "regional",        "label": "Some users affected, others not (regional split)", "weight": {"regional": 3}},
            {"id": "jobs_delayed",    "label": "Background jobs or notifications delayed",         "weight": {"queue": 2}},
            {"id": "total_outage",    "label": "Complete service unavailability",                  "weight": {"severity": 3}},
        ],
    },
    {
        "id":    "q_telemetry",
        "layer": "telemetry_signals",
        "text":  "Which telemetry signals are elevated right now?",
        "type":  "multi",
        "options": [
            {"id": "latency_up",    "label": "Latency / response time increasing",    "weight": {"latency": 2}},
            {"id": "error_rate",    "label": "Error rate rising",                     "weight": {"errors": 2}},
            {"id": "timeouts_up",   "label": "Timeout rate increasing",               "weight": {"timeouts": 2}},
            {"id": "retry_high",    "label": "Retry rate unusually high",             "weight": {"retries": 3}},
            {"id": "queue_grow",    "label": "Queue depth growing faster than normal","weight": {"queue": 3}},
            {"id": "cpu_high",      "label": "CPU or memory pressure",                "weight": {"resources": 2}},
            {"id": "cache_drop",    "label": "Cache hit rate dropping",               "weight": {"cache": 3}},
            {"id": "no_data",       "label": "Monitoring is unavailable or unclear",  "weight": {}},
        ],
    },
    {
        "id":    "q_trigger",
        "layer": "triggering_events",
        "text":  "What happened before this started?",
        "type":  "single",
        "options": [
            {"id": "deploy",       "label": "Recent deployment or configuration change",     "weight": {"deploy": 3}},
            {"id": "traffic",      "label": "Unexpected traffic spike or load increase",     "weight": {"traffic": 3}},
            {"id": "dependency",   "label": "Third-party service or dependency slowed down", "weight": {"dependency": 3}},
            {"id": "hardware",     "label": "Infrastructure or hardware event",              "weight": {"hardware": 3}},
            {"id": "external",     "label": "External event (weather, outage, regulation)",  "weight": {"external": 3}},
            {"id": "nothing",      "label": "Nothing obvious changed",                       "weight": {"unknown": 1}},
        ],
    },
    {
        "id":    "q_structural",
        "layer": "structural_conditions",
        "text":  "Which of these describe your infrastructure right now?",
        "type":  "multi",
        "options": [
            {"id": "single_dep",    "label": "One service or datastore that everything depends on", "weight": {"spof": 3}},
            {"id": "no_failover",   "label": "No automatic failover or redundancy",                "weight": {"spof": 2}},
            {"id": "bad_retries",   "label": "Services retry aggressively without backoff",        "weight": {"retries": 3}},
            {"id": "scale_limited", "label": "Auto-scaling is limited or turned off",              "weight": {"capacity": 3}},
            {"id": "no_circuit",    "label": "No circuit breakers configured",                     "weight": {"retries": 2}},
            {"id": "reduced_redun", "label": "Redundancy was recently reduced to cut costs",       "weight": {"cost": 3, "spof": 2}},
        ],
    },
    {
        "id":    "q_external",
        "layer": "external_drivers",
        "text":  "Are any of these broader pressures at play?",
        "type":  "multi",
        "options": [
            {"id": "cost_cut",    "label": "Recent cost-cutting or resource reduction",          "weight": {"cost": 3}},
            {"id": "understaffed","label": "Team is understaffed or under delivery pressure",    "weight": {"ops": 2}},
            {"id": "vendor_issue","label": "Cloud provider or vendor capacity constraint",       "weight": {"vendor": 3}},
            {"id": "regulatory",  "label": "New regulation or compliance requirement",           "weight": {"regulatory": 3}},
            {"id": "geo_event",   "label": "Geopolitical event or sanctions affecting a vendor", "weight": {"geopolitical": 3}},
            {"id": "none",        "label": "None of the above",                                  "weight": {}},
        ],
    },
]


# ── Scenario scoring matrix ───────────────────────────────────────────────────
# Each scenario gets a base score, then weights are added from user responses.
# Highest score wins.

SCENARIO_SIGNALS = {
    "retry_storm":           {"retries": 4, "errors": 3, "latency": 2, "deploy": 2, "bad_retries": 3, "no_circuit": 3},
    "dns_degradation":       {"timeouts": 4, "latency": 3, "dependency": 3, "latency_up": 2},
    "queue_backlog":         {"queue": 4, "resources": 3, "latency": 2, "traffic": 2, "scale_limited": 3, "jobs_delayed": 3},
    "regional_divergence":   {"regional": 4, "errors": 2, "hardware": 2, "no_failover": 2},
    "hurricane_datacenter":  {"external": 4, "hardware": 3, "resources": 2},
    "power_grid_brownout":   {"external": 4, "resources": 3, "latency": 2},
    "seismic_failure":       {"external": 4, "hardware": 4, "errors": 3, "severity": 3},
    "bgp_route_leak":        {"latency": 4, "timeouts": 3, "dependency": 2, "errors": 2},
    "regulatory_reroute":    {"regulatory": 5, "latency": 2},
    "cdn_sanctions":         {"geopolitical": 5, "latency": 3, "errors": 2, "dependency": 2},
    "vendor_capacity_crunch":{"vendor": 4, "capacity": 3, "resources": 3, "scale_limited": 3, "queue": 2},
    "cost_cut_redundancy":   {"cost": 4, "spof": 4, "reduced_redun": 4, "errors": 3, "severity": 2},
    "healthy_baseline":      {},
}


def diagnose(responses: dict) -> dict:
    """
    Run diagnostic logic from user responses.

    Parameters
    ----------
    responses : {question_id: [option_id, ...] or option_id}

    Returns
    -------
    Full chain analysis dict with matched scenario, layer findings,
    risk summary, and mitigation plan.
    """
    # ── Build signal vector from responses ───────────────────────────────
    signals = {}
    selected_option_ids = set()

    for q in QUESTIONS:
        ans = responses.get(q["id"], [])
        if isinstance(ans, str):
            ans = [ans]
        for opt in q["options"]:
            if opt["id"] in ans:
                selected_option_ids.add(opt["id"])
                for sig, wt in opt.get("weight", {}).items():
                    signals[sig] = signals.get(sig, 0) + wt

    # ── Score each scenario ───────────────────────────────────────────────
    scenario_scores = {}
    for scenario_id, sig_weights in SCENARIO_SIGNALS.items():
        score = 0
        for sig, weight in sig_weights.items():
            if sig in signals:
                score += signals[sig] * weight
            elif sig in selected_option_ids:
                score += weight
        scenario_scores[scenario_id] = score

    matched_scenario = max(scenario_scores, key=scenario_scores.get)
    match_confidence = scenario_scores[matched_scenario]

    if match_confidence < 4:
        matched_scenario = "healthy_baseline"

    # ── Build chain analysis ──────────────────────────────────────────────
    chain = _build_chain_analysis(matched_scenario, responses, signals, selected_option_ids)

    # ── Risk level ────────────────────────────────────────────────────────
    severity = signals.get("severity", 0)
    err_score = signals.get("errors", 0) + signals.get("timeouts", 0)
    infra_score = signals.get("spof", 0) + signals.get("cost", 0)

    total = severity * 2 + err_score + signals.get("latency", 0) + infra_score
    risk_score = min(1.0, total / 28.0)

    from engine.scoring import get_state, STATE_COLORS
    risk_state = get_state(risk_score)
    risk_color = STATE_COLORS[risk_state]

    # ── Mitigation ────────────────────────────────────────────────────────
    mitigation = _build_mitigation(matched_scenario, chain, signals)

    # ── Summary paragraph ─────────────────────────────────────────────────
    summary = _build_summary(matched_scenario, chain, signals)

    return {
        "matched_scenario": matched_scenario,
        "match_confidence": match_confidence,
        "risk_score":       round(risk_score, 3),
        "risk_state":       risk_state,
        "risk_color":       risk_color,
        "chain":            chain,
        "summary":          summary,
        "mitigation":       mitigation,
        "signals_detected": signals,
    }


def _build_chain_analysis(scenario, responses, signals, selected_ids):
    """Populate each of the 7 layers with identified factors."""
    chain = {}

    # Layer 0: External Drivers
    ext_factors = []
    q_ext = responses.get("q_external", [])
    if isinstance(q_ext, str): q_ext = [q_ext]
    factor_map_0 = {
        "cost_cut":     "Budget pressure or cost-cutting decisions",
        "understaffed": "Understaffed operations or delivery pressure",
        "vendor_issue": "Cloud provider capacity constraint",
        "regulatory":   "Regulatory or compliance mandate",
        "geo_event":    "Geopolitical event or vendor sanctions",
    }
    for opt_id, label in factor_map_0.items():
        if opt_id in q_ext:
            ext_factors.append(label)

    if scenario in ("hurricane_datacenter", "power_grid_brownout", "seismic_failure"):
        ext_factors.insert(0, "Physical infrastructure event (natural disaster)")
    if scenario == "bgp_route_leak":
        ext_factors.insert(0, "Network infrastructure anomaly (BGP routing)")

    chain["layer_0"] = {
        "layer":   LAYER_BY_ID["external_drivers"],
        "factors": ext_factors,
        "active":  len(ext_factors) > 0,
    }

    # Layer 1: Structural Conditions
    struct_factors = []
    q_struct = responses.get("q_structural", [])
    if isinstance(q_struct, str): q_struct = [q_struct]
    factor_map_1 = {
        "single_dep":    "Single dependency — too many services depend on one component",
        "no_failover":   "No automatic failover or redundancy configured",
        "bad_retries":   "Aggressive retry policies without exponential backoff",
        "scale_limited": "Auto-scaling limited or disabled",
        "no_circuit":    "No circuit breakers protecting dependent services",
        "reduced_redun": "Redundancy recently reduced to cut operational costs",
    }
    for opt_id, label in factor_map_1.items():
        if opt_id in q_struct:
            struct_factors.append(label)

    # Infer from scenario
    scenario_structural = {
        "retry_storm":          ["Aggressive retry policy", "No circuit breaker on auth dependency"],
        "cost_cut_redundancy":  ["Redundancy reduced — single-node cache", "No fallback path configured"],
        "vendor_capacity_crunch": ["Autoscaling cap insufficient for demand", "Reserved capacity underprovided"],
        "dns_degradation":      ["No secondary DNS resolver configured", "Service discovery relies on DNS only"],
    }
    for factor in scenario_structural.get(scenario, []):
        if factor not in struct_factors:
            struct_factors.append(factor)

    chain["layer_1"] = {
        "layer":   LAYER_BY_ID["structural_conditions"],
        "factors": struct_factors,
        "active":  len(struct_factors) > 0,
    }

    # Layer 2: Triggering Events
    trigger_factors = []
    q_trig = responses.get("q_trigger", "")
    trigger_labels = {
        "deploy":      "Deployment or configuration change preceded the incident",
        "traffic":     "Unexpected traffic spike or load increase",
        "dependency":  "Third-party service or dependency degraded",
        "hardware":    "Infrastructure or hardware event",
        "external":    "External physical or geopolitical event",
        "nothing":     "No obvious trigger identified — latent failure",
    }
    if q_trig in trigger_labels:
        trigger_factors.append(trigger_labels[q_trig])

    scenario_triggers = {
        "retry_storm":          ["Auth service failure (new deployment)"],
        "dns_degradation":      ["DNS resolver began experiencing timeouts"],
        "queue_backlog":        ["Consumer processing rate fell below ingestion rate"],
        "regional_divergence":  ["Worker cluster in secondary region began failing"],
        "hurricane_datacenter": ["Hurricane made landfall near datacenter cluster"],
        "seismic_failure":      ["Earthquake triggered automatic seismic shutdown"],
        "bgp_route_leak":       ["Misconfigured BGP peer announced incorrect routes globally"],
        "regulatory_reroute":   ["Data sovereignty regulation enforcement began"],
        "cdn_sanctions":        ["CDN provider placed under sanctions — emergency cutover required"],
        "vendor_capacity_crunch": ["Cloud provider issued InstanceLimitExceeded — no available capacity"],
        "cost_cut_redundancy":  ["Redundant cache node failed — no backup available"],
        "power_grid_brownout":  ["Regional power authority issued brownout notice"],
    }
    for t in scenario_triggers.get(scenario, []):
        if t not in trigger_factors:
            trigger_factors.append(t)

    chain["layer_2"] = {
        "layer":   LAYER_BY_ID["triggering_events"],
        "factors": trigger_factors,
        "active":  len(trigger_factors) > 0,
    }

    # Layer 3: Internal Stress Mechanics
    stress_factors = []
    q_tel = responses.get("q_telemetry", [])
    if isinstance(q_tel, str): q_tel = [q_tel]

    if "retry_high" in q_tel:
        stress_factors.append("Retries multiplying request volume across service boundaries")
    if "queue_grow" in q_tel:
        stress_factors.append("Queue depth growing faster than workers can drain")
    if "cpu_high" in q_tel:
        stress_factors.append("Worker or database connections falling behind under load")
    if "cache_drop" in q_tel:
        stress_factors.append("Cache collapse driving increased backend pressure")

    scenario_stress = {
        "retry_storm":          ["Retry amplification: each auth failure generates 5× retry load",
                                 "API gateway thread pool saturation"],
        "queue_backlog":        ["Queue consumer saturation — workers cannot scale further",
                                 "Database connection pool pressure from worker retries"],
        "dns_degradation":      ["Timeout clustering across all DNS-dependent service calls"],
        "seismic_failure":      ["Connection drops causing immediate cascading failure",
                                 "No graceful shutdown — in-flight requests abandoned"],
        "cost_cut_redundancy":  ["Cache miss storm — all reads falling through to database",
                                 "Database connection exhaustion under direct load"],
        "vendor_capacity_crunch": ["Worker saturation — existing instances at 99% CPU",
                                   "Queue depth building as workers cannot scale"],
        "hurricane_datacenter": ["Thermal throttling reducing effective compute capacity",
                                 "Network packet loss increasing retry load on internal calls"],
        "bgp_route_leak":       ["Traffic taking 3–5 extra AS hops — exponential latency increase"],
    }
    for factor in scenario_stress.get(scenario, []):
        if factor not in stress_factors:
            stress_factors.append(factor)

    chain["layer_3"] = {
        "layer":   LAYER_BY_ID["stress_mechanics"],
        "factors": stress_factors,
        "active":  len(stress_factors) > 0,
    }

    # Layer 4: Telemetry Signals
    tel_factors = []
    tel_labels = {
        "latency_up":  "Response latency climbing (p95/p99)",
        "error_rate":  "Error rate rising across affected services",
        "timeouts_up": "Timeout rate increasing — clustering against same dependency",
        "retry_high":  "Retry rate elevated — clients amplifying load",
        "queue_grow":  "Queue depth growing faster than drain rate",
        "cpu_high":    "CPU or memory saturation on compute nodes",
        "cache_drop":  "Cache hit rate falling — backend pressure increasing",
        "no_data":     "Monitoring data unavailable — blind to current state",
    }
    for opt_id, label in tel_labels.items():
        if opt_id in q_tel:
            tel_factors.append(label)

    chain["layer_4"] = {
        "layer":   LAYER_BY_ID["telemetry_signals"],
        "factors": tel_factors,
        "active":  len(tel_factors) > 0,
    }

    # Layer 5: User Degradation
    user_factors = []
    q_user = responses.get("q_user_impact", [])
    if isinstance(q_user, str): q_user = [q_user]
    user_labels = {
        "slow_pages":   "Pages and API responses loading slowly",
        "errors":       "Users seeing errors or failed requests",
        "timeouts":     "Requests timing out — users getting no response",
        "regional":     "Degraded experience isolated to specific regions",
        "jobs_delayed": "Background jobs, notifications, or reports delayed",
        "total_outage": "Service completely unavailable",
    }
    for opt_id, label in user_labels.items():
        if opt_id in q_user:
            user_factors.append(label)

    chain["layer_5"] = {
        "layer":   LAYER_BY_ID["user_degradation"],
        "factors": user_factors,
        "active":  len(user_factors) > 0,
    }

    # Layer 6: Business Impact (derived from user impact + risk)
    biz_factors = []
    if "total_outage" in q_user or "severity" in signals:
        biz_factors.append("Revenue at risk — user-facing services unavailable")
    if "errors" in q_user:
        biz_factors.append("SLA violation risk — error rate exceeding contractual thresholds")
    if "regional" in q_user:
        biz_factors.append("Customer trust at risk in affected geography")
    if "jobs_delayed" in q_user:
        biz_factors.append("Operational pipeline delay — downstream systems affected")
    if "regulatory" in signals:
        biz_factors.append("Regulatory compliance exposure — potential fine or audit risk")

    if not biz_factors:
        biz_factors.append("Performance degradation may impact customer satisfaction")

    chain["layer_6"] = {
        "layer":   LAYER_BY_ID["business_impact"],
        "factors": biz_factors,
        "active":  True,
    }

    return chain


def _build_summary(scenario, chain, signals):
    """Build a plain-language summary of what happened."""
    summaries = {
        "retry_storm": (
            "An auth service failure triggered aggressive client retries. "
            "Each failed request generated multiple retry attempts, multiplying load on the API gateway "
            "until its thread pool saturated. The problem originated in a deployment without a "
            "circuit breaker — a structural gap that turned a single service failure into a cascade."
        ),
        "dns_degradation": (
            "DNS resolver degradation is causing timeout clustering across services that depend on "
            "name resolution. The absence of a secondary resolver and DNS-independent service discovery "
            "means there is no automatic fallback. Latency is drifting before hard error rates climb — "
            "this is still in the weak-signal phase."
        ),
        "queue_backlog": (
            "Message ingestion is exceeding worker processing capacity. "
            "The queue is building faster than workers can drain it — a pattern driven by capped "
            "auto-scaling and insufficient reserved capacity. Workers are saturating, "
            "putting database connections and downstream services under increasing load."
        ),
        "hurricane_datacenter": (
            "A physical infrastructure event near the datacenter cluster is causing thermal stress "
            "and power instability. CPU throttling is reducing effective compute capacity across all "
            "services. Network degradation on coastal fiber routes is adding timeout pressure. "
            "This chain originates outside software — in the physical world."
        ),
        "seismic_failure": (
            "A seismic event caused immediate power loss to the affected datacenter zone. "
            "There was no graceful shutdown — in-flight requests were dropped. The failure propagated "
            "rapidly through dependent services because no redundant zone was active at the moment "
            "of impact. Recovery requires failover to an unaffected region."
        ),
        "bgp_route_leak": (
            "A misconfigured BGP peer is announcing incorrect routes, causing global traffic "
            "misdirection. Packets are traveling 3–5 extra network hops, inflating latency "
            "and causing timeout clustering. This is a network-layer failure — the application "
            "stack is functioning correctly, but the traffic cannot reach it efficiently."
        ),
        "regional_divergence": (
            "A subset of your worker infrastructure in a secondary region is degrading. "
            "Traffic is being routed inconsistently — some users hit healthy nodes, others do not. "
            "Database replication lag is growing. The system appears partially healthy from "
            "aggregate metrics but is failing for a portion of your user base."
        ),
        "cost_cut_redundancy": (
            "A single-node cache failure exposed a critical gap left by recent redundancy reduction. "
            "With no failback path, all reads are now hitting the database directly, overwhelming "
            "its connection pool. This failure was predictable — the structural condition was created "
            "when redundant nodes were removed to cut costs."
        ),
        "regulatory_reroute": (
            "A data sovereignty regulation is forcing traffic through a longer, compliant path. "
            "There is no hard failure — but latency is increasing steadily as cross-region database "
            "reads become required for all affected users. SLO erosion will continue until "
            "compliant infrastructure is provisioned closer to the affected user population."
        ),
        "cdn_sanctions": (
            "Sanctions against your primary CDN provider forced an emergency failover to a secondary "
            "CDN with significantly higher latency and fewer edge locations. "
            "The cutover introduced a spike as DNS propagated globally. Performance is now stabilizing "
            "at a degraded-but-functional baseline on the secondary CDN."
        ),
        "vendor_capacity_crunch": (
            "Your cloud provider is capacity-constrained in this region — likely due to AI compute demand. "
            "Auto-scaling requests are returning InstanceLimitExceeded. Your existing worker fleet is "
            "running at 99% CPU utilization with no ability to scale. Queue depth is building. "
            "This is an economic and physical constraint — not a software failure."
        ),
        "power_grid_brownout": (
            "A regional power authority brownout notice is causing voltage reduction across the datacenter. "
            "Servers are throttling CPU frequency to prevent hardware damage. All services are slowing "
            "uniformly — not because of a software failure, but because of reduced physical compute capacity. "
            "Queue depth is building as processing slows system-wide."
        ),
        "healthy_baseline": (
            "Based on the information provided, no significant failure pattern was identified. "
            "The signals you described are consistent with normal operational variation. "
            "Continue monitoring and re-evaluate if signals persist or intensify."
        ),
    }
    return summaries.get(scenario, "Analyzing failure pattern based on provided signals.")


def _build_mitigation(scenario, chain, signals):
    """Build a structured mitigation plan."""
    plans = {
        "retry_storm": {
            "now": [
                "Enable circuit breaker on auth service RIGHT NOW — this stops retry fan-out. "
                "In AWS: set ALB target group deregistration delay to 0 and health check threshold to 1. "
                "In Kubernetes with Istio: apply an OutlierDetection resource with consecutiveErrors: 1. "
                "Without this single action, load continues multiplying every 60 seconds.",
                "Apply exponential backoff with jitter immediately to all retry clients: "
                "base 100ms, multiplier 2×, cap 10s, ±30% jitter. "
                "In Node.js: use `axios-retry` with `exponentialDelay`. "
                "In Python: use `tenacity` with `wait_exponential(min=0.1, max=10, multiplier=2)`. "
                "This reduces retry load by ~80% within 90 seconds of deployment.",
                "Enforce a retry budget across all callers: max 2 retries per original request per hop. "
                "This caps amplification at 3× per service instead of unbounded. "
                "Enforce via API Gateway policy (AWS: add MaxRetries attribute to integration) "
                "or via service mesh timeout policy.",
            ],
            "next": [
                "Roll back the auth deployment that preceded the failure — do not patch forward. "
                "Verify rollback succeeded by watching auth error rate drop below 1% for 5 consecutive minutes "
                "before you consider the incident mitigated. Confirm the deployment pipeline gate was bypassed.",
                "Audit ALL service retry configurations in your codebase — search for `retry` and `maxRetries`. "
                "Standardize every service to the same exponential backoff policy. "
                "Create a company-wide retry configuration library so every team uses the same defaults.",
                "Add auth service error rate to your deployment pipeline gate. "
                "A deploy should fail automatically if auth error rate exceeds 2% during canary rollout. "
                "This would have caught this specific regression before it became an incident.",
            ],
            "prevent": [
                "Implement bulkhead pattern: isolate the auth service thread pool from API Gateway. "
                "Configure API Gateway to use a dedicated connection pool for auth calls (max: 50 connections) "
                "separate from the general upstream pool. A circuit breaker at the bulkhead boundary "
                "ensures auth failure can never exhaust the shared pool.",
                "Add retry-rate spike alerting: alert when retry rate exceeds 3× baseline for 60 seconds. "
                "This fires ~4 minutes earlier than error-rate alerting, before cascade begins. "
                "In Datadog: `sum:service.retry_count{*}.as_rate() > 3 * ${baseline_retry_rate}`.",
                "Require circuit breaker configuration review as part of every new service deployment PR. "
                "Build a linter or policy check (OPA/Conftest) that rejects deployments without "
                "circuit breaker configuration in the service manifest.",
            ],
        },
        "dns_degradation": {
            "now": [
                "Flush DNS resolver cache and manually switch to secondary resolver: "
                "In Linux: `systemd-resolve --flush-caches` then update `/etc/resolv.conf` to secondary. "
                "In AWS Route 53 Resolver: update inbound endpoint to secondary resolver IP. "
                "This moves traffic off the degraded resolver in under 60 seconds.",
                "Reduce TTL to 30s on all critical service A/CNAME records immediately. "
                "This accelerates propagation of any recovery update. "
                "In Route 53: `aws route53 change-resource-record-sets` with TTL: 30. "
                "Revert to normal TTL (300s) once degradation resolves.",
                "Monitor resolver response time every 10 seconds — if secondary resolver also shows >200ms, "
                "failover to anycast DNS (1.1.1.1 or 8.8.8.8 as emergency tertiary). "
                "This is a last resort for public services; private services may need a VPC resolver workaround.",
            ],
            "next": [
                "Configure automatic DNS failover: set up health checks on both primary and secondary resolvers "
                "and use a Route 53 failover routing policy to automatically switch on resolver degradation. "
                "Test failover quarterly — DNS failover is notoriously undertested.",
                "Add DNS resolver response time (p95) to your primary SLO monitoring dashboard. "
                "Alert at >100ms resolver latency — this fires well before user-visible DNS failures begin.",
            ],
            "prevent": [
                "Evaluate a sidecar service mesh (Istio, Linkerd, Consul Connect) for internal service-to-service "
                "calls. Service mesh uses mTLS and direct IP routing — DNS resolution is not in the critical path "
                "for internal traffic, eliminating this failure class entirely for internal services.",
                "Implement DNS response caching at the application level for critical dependencies. "
                "Cache DNS resolutions for 60s in your service clients. This masks brief resolver outages "
                "without requiring changes to resolver infrastructure.",
            ],
        },
        "queue_backlog": {
            "now": [
                "Scale worker pool immediately: double your consumer instance count. "
                "In AWS ECS: `aws ecs update-service --desired-count <2x current>`. "
                "In Kubernetes: `kubectl scale deployment worker --replicas=<2x current>`. "
                "On AWS Lambda: increase reserved concurrency limit for the queue processor function. "
                "Expect 5–8 minutes for new workers to initialize and begin draining.",
                "Inspect dead-letter queue for stuck or poison messages that are blocking normal processing. "
                "In AWS SQS: check the DLQ in the console or via `aws sqs get-queue-attributes`. "
                "Purge or reprocess DLQ messages separately — do not let them block the main queue.",
                "Apply message TTL to cap queue depth: set MessageRetentionPeriod to 4 hours "
                "(down from default 4 days) to expire oldest messages if they represent stale work. "
                "Caution: only do this if stale messages have no business consequence.",
            ],
            "next": [
                "Increase autoscaling maximum instance count from current cap to 3× current max. "
                "Configure CloudWatch alarm on `ApproximateNumberOfMessagesVisible > 1000` to trigger scale-out. "
                "Review your scale-in cooldown period — it may be too aggressive and causing capacity oscillation.",
                "Review queue partition count (Kafka) or shard count (Kinesis). "
                "Adding partitions/shards increases maximum consumer parallelism. "
                "For SQS Standard: consumers can already scale horizontally without partition limits.",
            ],
            "prevent": [
                "Set a queue depth alert at 2× normal operating depth as early warning — this fires 30–60 "
                "minutes before you hit the saturation point visible today. "
                "Configure a separate alarm for ApproximateAgeOfOldestMessage > 5 minutes — this catches "
                "stalled processing before depth metrics reveal it.",
                "Submit capacity planning requests 2 weeks before any marketing campaign or product launch "
                "that will drive load spikes. Include queue depth projections in the capacity ask.",
            ],
        },
        "hurricane_datacenter": {
            "now": [
                "Initiate pre-emptive regional failover BEFORE the storm makes landfall — not after. "
                "In AWS: update Route 53 health check to manually fail primary region. "
                "Update weighted routing policy to direct 100% traffic to secondary. "
                "Verify secondary region has enough reserved capacity to absorb full load before cutting over.",
                "Shift 100% traffic to your secondary region via DNS weighted routing or load balancer. "
                "TTL on your DNS records must be ≤60s for this to propagate in time. "
                "If TTL is currently 300s+, pre-warm users by reducing TTL 24 hours before the storm window.",
                "Contact datacenter facility NOC to confirm generator fuel level and ETA for resupply. "
                "Generator fuel at typical load lasts 72 hours, but cooling overhead under storm conditions "
                "increases consumption ~30% — effective runway may be only 50 hours.",
            ],
            "next": [
                "Freeze all non-essential deployments for the duration of the storm window. "
                "A failed deployment during DR operation doubles your incident complexity. "
                "Communicate deployment freeze to all engineers via Slack/Teams immediately.",
                "Confirm on-call coverage continuity — physical access to the datacenter will be restricted "
                "during and after the storm. Identify who has remote access credentials for every critical system.",
            ],
            "prevent": [
                "Establish multi-region active-active architecture as a standard: no single region should be "
                "load-bearing. Use global load balancing (AWS Global Accelerator, GCP Global LB) to distribute "
                "traffic across regions under normal conditions so failover is seamless.",
                "Build a physical event runbook triggered by NOAA/NWS watch or warning in your datacenter geography. "
                "It should auto-alert your on-call team and pre-stage all DR steps 48 hours before impact.",
            ],
        },
        "seismic_failure": {
            "now": [
                "Initiate DR failover to your unaffected availability zone or region immediately. "
                "There is no recovery option in the failed zone — it has no power. "
                "In AWS: manually fail over Route 53 health check, redirect to us-west-2 or eu-west-1. "
                "Verify target region can accept 100% of load before completing the failover.",
                "Open incident bridge immediately and communicate to affected customers now. "
                "Post status page update: 'We are experiencing a datacenter infrastructure event and are "
                "failing over to our secondary region. ETA for restoration: 15–30 minutes.' "
                "Do not delay communications while you work the technical problem.",
                "Verify your surviving availability zone or region has at least 140% capacity "
                "to absorb the failed zone's traffic. Check auto-scaling group max instance limit "
                "and manually increase if needed before shifting traffic.",
            ],
            "next": [
                "After failover completes, validate database consistency rigorously. "
                "Run a consistency check on your primary database replica for signs of split-brain. "
                "If using PostgreSQL: check `pg_stat_replication` and replication lag. "
                "Do not declare recovery until database is confirmed consistent.",
                "Enumerate all in-flight transactions at the time of failure. "
                "For every transaction that was mid-commit, determine if it succeeded, rolled back, "
                "or is in an unknown state. This is required for accurate financial reconciliation.",
            ],
            "prevent": [
                "Implement active-active architecture across multiple availability zones (or regions). "
                "No single zone should carry more than 60% of traffic at any time — this allows "
                "automatic absorption of a zone failure without customer-visible impact.",
                "Test DR failover procedures quarterly via a live drill — not just tabletop exercises. "
                "Real failover tests expose missing automation and stale runbooks before an actual event.",
            ],
        },
        "bgp_route_leak": {
            "now": [
                "Contact your upstream ISP NOC immediately. Reference the leaking AS number and prefix. "
                "Use bgpstream.com or RIPE NCC Looking Glass to identify the leaking AS path in real time. "
                "ISP NOCs can deploy an emergency BGP filter in 5–15 minutes if they are engaged. "
                "Have the AS path and affected prefix ready when you call.",
                "Apply ingress filtering on your own border routers to reject route advertisements "
                "that do not pass RPKI validation. This is a partial mitigation until the leak is stopped. "
                "If you have multiple upstream ISPs, verify which one is propagating the leak and isolate it.",
                "Post a status page update with accurate messaging: "
                "'We are experiencing a network routing issue caused by a BGP route leak from a third-party "
                "network. Our application infrastructure is functioning correctly. ETA for resolution: "
                "15–45 minutes pending ISP action.' This manages customer expectations accurately.",
            ],
            "next": [
                "Deploy RPKI Route Origin Validation with your ISP. RPKI cryptographically validates "
                "that BGP route announcements come from authorized origin ASes — it would prevent this "
                "leak from propagating through your path. Implementation requires coordination with your ISP "
                "and typically takes 1–2 days.",
                "Configure max-prefix limits on all BGP peer sessions. "
                "A max-prefix limit causes the BGP session to tear down if a peer announces an abnormal "
                "number of prefixes — this is a standard defensive measure against accidental leaks.",
            ],
            "prevent": [
                "Subscribe to BGP anomaly monitoring: RIPE NCC BGP Analytics, Cloudflare Radar, or "
                "a commercial service like Kentik. These alert you to route changes affecting your prefixes "
                "within minutes — giving you time to respond before users are widely affected.",
                "Establish relationships with NOC contacts at your Tier-1 upstream ISPs. "
                "Having a direct phone number and email for ISP NOC engineers reduces response time "
                "from 45+ minutes (ticket queue) to 5–10 minutes (direct call).",
            ],
        },
        "regional_divergence": {
            "now": [
                "Shift traffic away from the degraded region using load balancer weight adjustment. "
                "In AWS: update the weighted target group to send 0% to the degraded region. "
                "In GCP: update backend service weights in the global load balancer. "
                "Monitor error rate for 2 minutes after the shift to confirm affected user population decreases.",
                "Check database replication lag for the degraded region. "
                "If replication lag exceeds 30 seconds, pause writes to that region to prevent data divergence. "
                "In AWS RDS: check `ReplicaLag` CloudWatch metric. In PostgreSQL: `SELECT * FROM pg_stat_replication`.",
                "Alert affected customers in the degraded geography if they are enterprise accounts with SLAs. "
                "Pro-active communication preserves trust. Post a status page entry indicating regional degradation.",
            ],
            "next": [
                "Investigate the root cause of the regional hardware degradation. "
                "Check cloud provider health dashboard for the affected AZ. "
                "If it is provider infrastructure: open a support ticket and request instance migration. "
                "If it is your hardware: initiate a hardware replacement request through your datacenter NOC.",
                "Update your multi-region failover runbook — it is currently stale. "
                "Document what happened today (what worked, what didn't) and update the runbook to reflect "
                "the actual steps required. Assign a date for the next quarterly failover drill.",
            ],
            "prevent": [
                "Implement automated regional health checks with automatic traffic shifting. "
                "Use AWS Route 53 Health Checks + failover routing, or GCP Traffic Director health policies, "
                "to automatically remove a region from the rotation when its error rate exceeds threshold.",
                "Establish quarterly multi-region failover drills. Each drill should include a live traffic shift, "
                "database replication validation, and a 15-minute production test on the secondary region.",
            ],
        },
        "cost_cut_redundancy": {
            "now": [
                "Provision a replacement cache replica immediately. In AWS ElastiCache: "
                "`aws elasticache create-replication-group --replication-group-id <id>`. "
                "This takes 5–10 minutes. In the interim, add a DB connection pool limit of 30 per service "
                "to prevent full connection exhaustion while cache is warming up. "
                "Do NOT restart the database — that will extend the outage by 10–20 minutes.",
                "Rate-limit inbound API traffic at the load balancer to protect the database. "
                "In AWS ALB: add a WAF rate limit rule of 50% normal request rate. "
                "This throttles new requests but prevents the database from crashing entirely — "
                "a crashed database requires 10–15 minutes to restart versus staying degraded.",
                "Enable read replica routing for non-critical read queries (product catalog, user preferences). "
                "Even if your read replica is under-provisioned, offloading 30–40% of reads buys time. "
                "In Rails: set `ApplicationRecord.establish_connection(:replica)` for read-only controllers.",
            ],
            "next": [
                "Restore redundant cache configuration — this is non-negotiable. "
                "Provision 2 cache replicas in separate AZs (primary + 1 replica minimum). "
                "The monthly cost of a Redis replica ($30–$500 depending on instance size) is trivially "
                "less than the revenue loss from a single hour of this incident.",
                "Add a circuit breaker between API gateway and the cache layer. "
                "If the cache becomes unavailable, the circuit breaker should fail open to a reduced-capacity "
                "mode (serve from DB with connection limits) rather than crashing your entire service.",
            ],
            "prevent": [
                "Require a written reliability review before ANY infrastructure cost-reduction change. "
                "The review must include: single-point-of-failure analysis, failure mode simulation, "
                "and sign-off from both the platform team and the team that owns the affected services. "
                "This is a process control — it would have caught this specific change before it was made.",
                "Run quarterly chaos engineering drills targeting single-node failure for every "
                "infrastructure component flagged as redundancy-reduced. "
                "Use AWS Fault Injection Simulator or Gremlin to inject the failure and validate "
                "that the system degrades gracefully rather than failing completely.",
            ],
        },
        "vendor_capacity_crunch": {
            "now": [
                "Attempt scale-out using a different instance family or type in the same region. "
                "AWS capacity exhaustion is typically type-specific: if c5.2xlarge is exhausted, "
                "try c6i.2xlarge, m5.2xlarge, or Graviton (c7g.2xlarge). Use AWS Instance Type Explorer "
                "to find available types with equivalent vCPU/RAM. Change your autoscaling group launch template now.",
                "Contact cloud provider enterprise support immediately with your account ID and the "
                "exact error code (InsufficientCapacityException or equivalent). "
                "Enterprise support can submit a capacity reservation request to the regional capacity team "
                "and often resolves this in 15–30 minutes. Business support: 4-hour SLA; Enterprise: 1-hour.",
                "Apply request queuing and shedding at your API gateway to protect existing worker fleet. "
                "Return HTTP 429 (Too Many Requests) with Retry-After: 30 for requests that exceed worker capacity. "
                "This prevents queue depth from growing beyond a recoverable threshold.",
            ],
            "next": [
                "Purchase On-Demand Capacity Reservations (ODCR) for your baseline instance types in all "
                "critical regions. ODCRs guarantee capacity even during regional shortages — you pay for "
                "the reservation whether you use it or not, but your baseline is always available.",
                "Evaluate multi-cloud or multi-instance-family worker deployment to eliminate "
                "single-provider dependency. Configure your autoscaling to prefer one cloud but overflow "
                "to a secondary provider (AWS + GCP, or AWS us-east-1 + us-west-2) when capacity is constrained.",
            ],
            "prevent": [
                "Monitor cloud provider capacity signals proactively. "
                "AWS Capacity Blocks, GCP Commitment availability — subscribe to provider health feeds. "
                "Build a 30% capacity buffer above peak load using Reserved Instances or Committed Use Discounts.",
                "Run a quarterly capacity drill: intentionally scale down to zero reserved capacity and "
                "attempt to scale back up from on-demand only. This tests your actual capacity assumptions "
                "under real market conditions.",
            ],
        },
        "regulatory_reroute": {
            "now": [
                "Communicate the latency increase to affected enterprise customers immediately "
                "with explicit SLO context: 'We are experiencing a 40–80ms latency increase for users in "
                "[jurisdiction] due to a new data sovereignty compliance requirement. This is expected to "
                "persist until we provision compliant infrastructure, estimated [date].'",
                "Provision compliant data infrastructure in the affected jurisdiction as the highest-priority "
                "engineering task. Estimate: 2–4 weeks for a read replica in-region; 6–12 weeks for "
                "full data residency compliance. Get an engineering estimate today and communicate it upward.",
            ],
            "next": [
                "Renegotiate SLA terms with customers in the affected geography to reflect the new latency baseline. "
                "Most enterprise contracts have force-majeure provisions that cover regulatory compliance changes. "
                "Engage your legal and account management teams within 48 hours.",
                "Evaluate edge caching and read replica strategies to minimize cross-region database reads. "
                "For user profile and session data: a compliant read replica in-region reduces latency "
                "by 40–70ms for most queries.",
            ],
            "prevent": [
                "Subscribe to legal and regulatory intelligence services for all operating jurisdictions. "
                "GDPR, CCPA, and emerging data sovereignty laws have 6–18 month implementation windows — "
                "enough time to prepare compliant infrastructure before the effective date.",
                "Design your data architecture for jurisdiction-awareness from the start. "
                "Implement a data residency layer that routes reads and writes to the correct regional store "
                "based on user jurisdiction metadata. This is table stakes for global operations.",
            ],
        },
        "cdn_sanctions": {
            "now": [
                "Confirm secondary CDN is receiving traffic and serving correctly. "
                "Check your secondary CDN dashboard for cache hit rate — it may be near 0% on cold start. "
                "Warm critical assets (homepage, login page, main JS/CSS bundles) by pre-fetching them "
                "via the CDN API. This improves performance within 5–10 minutes.",
                "Reduce DNS TTL aggressively to 30 seconds to accelerate client cutover to the secondary CDN. "
                "In Route 53: update your CDN CNAME TTL. Note: existing DNS caches will persist for "
                "up to the previous TTL — full propagation takes ~5 minutes at this TTL.",
                "Post a status page update with honest, forward-looking messaging. "
                "Acknowledge the performance degradation, attribute it to a CDN infrastructure change, "
                "and give a realistic timeline for optimization. Avoid mentioning the specific vendor.",
            ],
            "next": [
                "Onboard a third CDN vendor as a cold standby. "
                "Akamai, Fastly, CloudFront, and Bunny CDN each have different geopolitical exposure. "
                "A two-CDN strategy (active + warm standby) with pre-tested failover reduces cutover time "
                "from 4–6 hours to under 15 minutes in future events.",
                "Pre-negotiate emergency CDN contracts with at least one alternative provider. "
                "Include SLA terms for activation time and performance guarantees for your top traffic regions.",
            ],
            "prevent": [
                "Subscribe to geopolitical risk intelligence relevant to your vendor portfolio. "
                "CDN sanctions events have had 24–72 hour warning windows in historical cases. "
                "A risk monitoring feed lets you pre-position on a secondary CDN before the forced cutover.",
                "Implement multi-CDN routing as standard architecture using a traffic management layer "
                "(NS1, AWS Global Accelerator, or Cloudflare Load Balancing). "
                "Distribute 80/20 across two CDNs under normal operation — failover is instantaneous.",
            ],
        },
        "power_grid_brownout": {
            "now": [
                "Contact your datacenter facility team and get real-time fuel and UPS status. "
                "Standard 72-hour generator fuel + 30% cooling overhead = 52-hour effective window. "
                "If fuel is below 50%: arrange resupply now — delivery takes 4–12 hours in storm conditions.",
                "Shed non-critical batch workloads immediately to reduce power and thermal draw. "
                "Disable: ML inference jobs, analytics pipelines, nightly reports, image processing queues. "
                "Prioritize: checkout, auth, payment processing, critical APIs. "
                "Each shed workload reduces power draw by 5–15% and extends generator runway.",
                "Prepare for potential regional failover if brownout deepens to blackout. "
                "Pre-stage DNS failover configuration now — do not wait for the power to actually go out.",
            ],
            "next": [
                "Review your datacenter power contract for brownout/blackout provisions and SLA obligations. "
                "Most colo contracts have force-majeure clauses — document the event and notify your provider.",
                "Audit UPS (Uninterruptible Power Supply) runtime estimates against current power draw. "
                "UPS runtime degrades as batteries age — if batteries are >3 years old, runtime may be "
                "significantly lower than rated. Request a battery test from the facility team.",
            ],
            "prevent": [
                "Establish a direct relationship with your regional utility company for advance brownout notices. "
                "Utilities typically provide 24–72 hour warnings for planned brownouts. "
                "Subscribe to your utility's industrial alert list if one exists.",
                "Evaluate multi-region active-active architecture to shed load from power-stressed regions. "
                "With active-active, a 50% power reduction in one region means you need 50% more capacity "
                "in the surviving region — not a full failover.",
            ],
        },
        "healthy_baseline": {
            "now": [
                "No immediate action required. Current signals are within normal operating parameters. "
                "Continue monitoring at standard sampling rate.",
            ],
            "next": [
                "Verify alerting thresholds are correctly calibrated for your current traffic patterns. "
                "Thresholds should be reviewed quarterly as baseline metrics shift.",
            ],
            "prevent": [
                "Schedule a quarterly reliability review — review alerting coverage, SLO breach frequency, "
                "and failure mode documentation while systems are healthy.",
            ],
        },
    }

    default = {
        "now": ["Increase monitoring sampling rate to capture higher-resolution signal data",
                "Notify on-call team — set to active watch"],
        "next": ["Review recent deployment history — consider rollback if change preceded degradation"],
        "prevent": ["Conduct post-incident review within 48 hours"],
    }
    return plans.get(scenario, default)
