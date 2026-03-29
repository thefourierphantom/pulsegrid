# engine/recommendations.py
# PulseGrid rule-based recommendation engine
#
# Maps (scenario, system_state, service_scores, signal_breakdown)
# to ranked Immediate Actions and Optimization Opportunities.
#
# Design note: this is intentionally a transparent rule engine, not a black box.
# Every recommendation is traceable to a specific signal pattern.

from .scoring import STATE_ORDER


def _state_gte(state, minimum):
    """Returns True if state is at least as severe as minimum."""
    return STATE_ORDER.index(state) >= STATE_ORDER.index(minimum)


# ── Rule definitions ──────────────────────────────────────────────────────────
# Each rule: id, match_fn(scenario, system_state, svc_scores, sig_breakdown),
#            immediate[], optimize[], evidence_note

RULES = [
    {
        "id": "cascading_failure",
        "priority": 0,
        "match": lambda sc, st, ss, sb: st == "cascading",
        "immediate": [
            "Activate graceful degradation — serve cached/static fallbacks immediately",
            "FREEZE all deployments and config changes NOW",
            "Isolate failing dependency — disable non-critical downstream calls",
            "Open incident bridge and page on-call engineer",
        ],
        "optimize": [
            "Schedule blameless postmortem within 48 hours",
            "Implement chaos drills targeting this specific failure pattern",
            "Review blast-radius boundaries and add automatic circuit breakers",
        ],
        "note": "System is in full cascade. Containment takes priority over diagnostics.",
    },
    {
        "id": "retry_storm",
        "priority": 1,
        "match": lambda sc, st, ss, sb: (
            sc == "retry_storm" or
            any(sb.get(svc, {}).get("retry_amplify", 0) > 0.50 for svc in sb)
        ),
        "immediate": [
            "Enable circuit breaker on auth service — stop retry fan-out",
            "Apply exponential backoff with jitter (initial: 100ms, max: 10s)",
            "Enforce retry budget: max 2 retries per request across all clients",
        ],
        "optimize": [
            "Audit all service retry configurations — standardize to backoff policy",
            "Implement bulkhead pattern: isolate auth failures from API gateway thread pool",
            "Add retry-rate spike to primary alerting rules",
        ],
        "note": "Retry amplification detected. Each failed request is generating downstream storms.",
    },
    {
        "id": "dns_degradation",
        "priority": 2,
        "match": lambda sc, st, ss, sb: (
            sc == "dns_degradation" or
            (ss.get("api_gateway", 0) > 0.35 and ss.get("auth", 0) > 0.30
             and any(sb.get(svc, {}).get("timeout_cluster", 0) > 0.40
                     for svc in ("api_gateway", "auth")))
        ),
        "immediate": [
            "Activate DNS fallback — flush to cached resolver entries",
            "Reduce DNS TTL to 30s to accelerate propagation on recovery",
            "Switch to secondary DNS provider if primary resolver is unresponsive",
        ],
        "optimize": [
            "Pre-warm DNS cache on all critical service startup scripts",
            "Evaluate sidecar service mesh for DNS-independent discovery",
            "Add resolver response-time metric to primary SLO dashboard",
        ],
        "note": "Timeout clustering in API/auth path is consistent with DNS resolver degradation.",
    },
    {
        "id": "queue_backlog",
        "priority": 3,
        "match": lambda sc, st, ss, sb: (
            sc == "queue_backlog" or
            ss.get("queue", 0) > 0.40 or
            ss.get("worker", 0) > 0.40
        ),
        "immediate": [
            "Scale worker pool — provision 2× consumer instances immediately",
            "Inspect dead-letter queue for poison messages blocking processing",
            "Apply message TTL to prevent unbounded depth accumulation",
        ],
        "optimize": [
            "Implement autoscaling on queue depth metric (target: <100 messages)",
            "Add consumer throughput and lag monitoring to alerting dashboard",
            "Evaluate async-first design for non-critical write paths to reduce queue pressure",
        ],
        "note": "Workers cannot drain queue fast enough. Customer-facing latency will rise.",
    },
    {
        "id": "regional_divergence",
        "priority": 4,
        "match": lambda sc, st, ss, sb: sc == "regional_divergence",
        "immediate": [
            "Shift traffic away from degraded region — activate failover routing",
            "Freeze deployments until regional health parity is confirmed",
            "Verify cross-region replication lag — inspect database replica status",
        ],
        "optimize": [
            "Implement regional health checks in load balancer configuration",
            "Review traffic-split policies for automated failover trigger thresholds",
            "Add cross-region latency divergence to SLO monitoring",
        ],
        "note": "Regional divergence detected. Blast radius limited to affected zone.",
    },
    {
        "id": "general_instability",
        "priority": 5,
        "match": lambda sc, st, ss, sb: _state_gte(st, "unstable"),
        "immediate": [
            "Increase telemetry sampling rate — capture higher-resolution signal data",
            "Check recent deployment log — consider rollback if change preceded degradation",
            "Notify on-call team — set to active monitoring watch",
        ],
        "optimize": [
            "Review SLO error budget consumption rate against burn threshold",
            "Audit which services have no circuit breakers configured",
            "Schedule capacity review — validate autoscaling thresholds against current load",
        ],
        "note": "Multiple signals elevated. Pattern is consistent with early-stage degradation.",
    },
    {
        "id": "watch_advisory",
        "priority": 6,
        "match": lambda sc, st, ss, sb: st == "watch",
        "immediate": [
            "No immediate action required — continue passive monitoring",
            "Review signal trends over next 5 minutes before escalating",
        ],
        "optimize": [
            "Verify alert thresholds are tuned — current signals are approaching warning range",
            "Confirm on-call engineer is reachable if state escalates",
        ],
        "note": "Signals are drifting but no hard failure detected yet.",
    },
]


def get_recommendations(scenario: str, system_state: str, service_scores: dict,
                         signal_breakdown: dict) -> dict:
    """
    Match rules and return a ranked recommendation set.

    Parameters
    ----------
    scenario        : active scenario name (e.g., 'retry_storm')
    system_state    : current system-level state string
    service_scores  : {service_id: float score}
    signal_breakdown: {service_id: {signal_name: float}}

    Returns
    -------
    dict with matched_patterns, immediate_actions, optimization_opportunities,
         rationale, confidence
    """
    matched_immediate = []
    matched_optimize  = []
    matched_ids       = []
    notes             = []

    sorted_rules = sorted(RULES, key=lambda r: r["priority"])

    for rule in sorted_rules:
        try:
            if rule["match"](scenario, system_state, service_scores, signal_breakdown):
                matched_ids.append(rule["id"])
                notes.append(rule.get("note", ""))
                for a in rule["immediate"]:
                    if a not in matched_immediate:
                        matched_immediate.append(a)
                for a in rule["optimize"]:
                    if a not in matched_optimize:
                        matched_optimize.append(a)
        except Exception:
            pass

    return {
        "matched_patterns":           matched_ids,
        "immediate_actions":          matched_immediate[:6],
        "optimization_opportunities": matched_optimize[:4],
        "rationale":                  notes[:2],
        "confidence":                 "high" if matched_ids else "none",
    }
