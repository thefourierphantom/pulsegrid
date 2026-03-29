"""
engine/chatbot.py
PulseGrid AI — Unified incident intelligence brain.

Both diagnostic and scenario modes share the same domain-aware system prompt
and the same signal-extraction logic. The bot sounds like a senior SRE who has
seen every failure mode in the signal matrix, not a generic assistant.

Free-text bypass:
  When a user types a paragraph describing their incident instead of clicking
  through the 5-question wizard, _extract_and_diagnose() maps natural language
  to structured signals, calls diagnose(), and returns a full result so the
  frontend can jump directly to the results screen.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .chain import QUESTIONS, LAYERS, SCENARIO_SIGNALS, diagnose

# ── Domain knowledge constants ────────────────────────────────────────────────

SCENARIO_SUMMARIES = {
    "retry_storm": (
        "Retry Storm — A dependency failure (typically auth or a core API) triggers "
        "clients to retry immediately and aggressively. Without circuit breakers, each "
        "retry generates more load on an already-failing service. Retry volume multiplies "
        "5–10× in under 2 minutes, saturating thread pools and crashing adjacent services "
        "that share the same connection pool. P95 latency typically hits 8–15× baseline "
        "before the cascade completes."
    ),
    "dns_degradation": (
        "DNS Degradation — The DNS resolver begins timing out on some fraction of queries. "
        "Because service discovery depends entirely on DNS, every downstream call that "
        "misses its DNS lookup hangs until the client-side timeout fires. With no secondary "
        "resolver, timeout clusters build across all DNS-dependent services simultaneously. "
        "Median latency rises slowly at first, then spikes sharply as connection pools fill "
        "with hanging requests."
    ),
    "queue_backlog": (
        "Queue Backlog — Consumer processing rate falls below ingestion rate, usually due "
        "to a compute constraint or upstream traffic spike. Queue depth grows continuously. "
        "Background jobs, notifications, and async workflows start lagging minutes, then "
        "hours behind. Workers retry stale messages, adding pressure to the database. "
        "Without auto-scaling headroom, the gap never closes without explicit intervention."
    ),
    "regional_divergence": (
        "Regional Divergence — A worker cluster or availability zone begins failing while "
        "other regions stay healthy. Users in the affected region see elevated errors and "
        "latency; others do not. If traffic is not actively rerouted, the affected zone "
        "continues degrading while monitoring shows an aggregate 'mostly OK' signal that "
        "masks the real severity for a subset of users."
    ),
    "hurricane_datacenter": (
        "Hurricane / Physical Datacenter Event — An extreme weather event threatens or "
        "directly impacts a physical datacenter cluster. Thermal stress reduces compute "
        "capacity before power fails. Network packet loss increases retry-amplified internal "
        "load. If the facility must shut down, all services hosted there go dark unless "
        "failover to an alternate region was pre-staged and tested."
    ),
    "power_grid_brownout": (
        "Power Grid Brownout — Regional power authority reduces voltage supply, causing "
        "server CPUs to throttle and UPS systems to activate. Compute-intensive services "
        "slow first. If brownout deepens into full outage, any facility without N+1 generator "
        "capacity loses power and any in-flight transactions are lost."
    ),
    "seismic_failure": (
        "Seismic / Earthquake Failure — Automatic seismic shutdown systems trigger before "
        "or during an earthquake, cutting power to racks without graceful service termination. "
        "All in-flight requests are dropped. Dependent services see immediate connection resets "
        "and start generating their own error cascades. Recovery requires physical inspection "
        "before restart — remote recovery is not possible if structural damage occurred."
    ),
    "bgp_route_leak": (
        "BGP Route Leak — A misconfigured BGP peer announces incorrect or more-specific "
        "routes, attracting traffic that should flow through normal paths into a suboptimal "
        "AS path. Packets traverse 3–5 extra hops, adding 50–400ms per request depending "
        "on geographic distance. The effect looks like latency degradation on a dependency, "
        "but the root cause is in network routing, not the application layer."
    ),
    "regulatory_reroute": (
        "Regulatory Data Reroute — A new data sovereignty regulation or compliance enforcement "
        "action forces traffic to be rerouted away from previously used regions or providers. "
        "The reroute adds latency and may break assumptions baked into service endpoints, "
        "certificates, or data residency configurations. Recovery requires legal, platform, "
        "and engineering coordination simultaneously."
    ),
    "cdn_sanctions": (
        "CDN Sanctions Cutover — A CDN or edge provider is placed under sanctions, forcing "
        "an emergency migration to an alternate provider. During the cutover window, some "
        "edge nodes go dark, serving errors to users in affected regions. Static asset "
        "delivery and TLS termination may both be impacted. Time-to-full-recovery depends "
        "on TTL propagation and DNS cutover speed."
    ),
    "vendor_capacity_crunch": (
        "Vendor Capacity Crunch — The cloud provider has exhausted available instance capacity "
        "in the required region or family. Auto-scaling requests return InstanceLimitExceeded. "
        "Existing workers hit 99%+ CPU. Queue depth builds because no new workers can be "
        "launched to drain it. Recovery requires either a different instance family, a "
        "different region, or reserved capacity that was not pre-purchased."
    ),
    "cost_cut_redundancy": (
        "Cost-Cut Redundancy Failure — A redundant component (cache node, standby replica, "
        "or secondary AZ) was removed to reduce cost. When the primary fails, there is no "
        "fallback. All traffic hits the single remaining node or falls through to the database "
        "directly. Connection exhaustion follows rapidly. The blast radius is disproportionate "
        "to the trigger — a single node failure causes multi-service degradation."
    ),
    "healthy_baseline": (
        "Healthy Baseline — All services operating within normal parameters. No signals "
        "indicate active failure propagation."
    ),
}

STAT_BENCHMARKS = (
    "Industry benchmarks (PagerDuty State of Digital Operations, n=15,000+): "
    "median MTTD 14 min, median MTTR 4.2 hr for P1. "
    "Retry storms account for 23% of cascading failures (Google SRE Book). "
    "DNS-related failures resolve in median 28 min when resolver redundancy is added. "
    "Queue backlogs require 2–6× worker scaling to drain under continued ingestion. "
    "Blast radius propagation follows a 2-hop rule: direct dependencies absorb 60–80% "
    "of degradation, second-hop services absorb 20–40% (CNCF Survey 2023). "
    "Cost-reduction incidents have 2.3× higher MTTR than capacity failures (Atlassian). "
    "BGP route leaks produce median +180ms added latency per misrouted hop (RIPE NCC)."
)

MITIGATION_PLAYBOOKS = {
    "retry_storm": {
        "stop_bleeding": (
            "1. Enable circuit breaker on the failing dependency NOW — Istio: apply OutlierDetection "
            "with consecutiveErrors:1, interval:10s, baseEjectionTime:30s. AWS ALB: set "
            "deregistration delay to 0, unhealthy threshold to 1. Without this, retries keep "
            "multiplying every 60 seconds.\n"
            "2. Set retry budget to max 3 attempts with exponential backoff (base 100ms, cap 2s, "
            "jitter 0–50%). Apply at API gateway level: Kong: retries: 3, retry_on: 5xx,connect-failure. "
            "Nginx: proxy_next_upstream_tries 3.\n"
            "3. Drop the rate limit on the auth service to 50% of normal capacity at the load "
            "balancer to prevent thread pool saturation while the circuit breaker engages."
        ),
        "prevent_recurrence": (
            "Instrument a retry budget dashboard (Grafana: ratio of retried requests to first-attempt "
            "requests, alert at 20%). Add circuit breaker integration tests to your CI pipeline "
            "using Chaos Monkey or Gremlin. Require exponential backoff with jitter in your API "
            "client SDK standards document."
        ),
    },
    "dns_degradation": {
        "stop_bleeding": (
            "1. Add a secondary DNS resolver immediately. AWS: add a second Route 53 Resolver "
            "endpoint in a different AZ. On-prem: configure /etc/resolv.conf with options rotate "
            "and two nameserver entries. CoreDNS: add a forward block with two upstreams and "
            "health { lameduck 5s }.\n"
            "2. Reduce DNS TTL on all critical service records to 30 seconds to speed up "
            "future failover detection.\n"
            "3. Enable DNS response caching at the service mesh layer (Envoy: dns_cache_config "
            "with max_hosts 1024, dns_lookup_family AUTO) to absorb resolver outages for "
            "already-resolved names."
        ),
        "prevent_recurrence": (
            "Implement multi-resolver configuration as a platform standard. Add a DNS resolution "
            "SLO (99.9% of lookups resolve in <50ms) and alert on it. Consider service mesh "
            "sidecar discovery (Consul Connect, Istio) to reduce DNS as a hard dependency."
        ),
    },
    "queue_backlog": {
        "stop_bleeding": (
            "1. Scale consumers immediately: kubectl scale deployment queue-worker --replicas=N "
            "where N = current_queue_depth / (target_drain_rate_per_worker * drain_window_minutes). "
            "AWS SQS: increase Lambda reserved concurrency or ECS task count. "
            "If auto-scaling is limited, temporarily increase max instances in your ASG.\n"
            "2. Pause non-critical message producers to stop queue depth from growing while "
            "you drain. Use feature flags or producer-side rate limits.\n"
            "3. Prioritize message processing: if your queue supports priority, bump time-sensitive "
            "messages (order confirmations, auth tokens) above analytics/notification payloads."
        ),
        "prevent_recurrence": (
            "Set a queue depth alarm at 2× normal peak depth (CloudWatch: ApproximateNumberOfMessagesVisible). "
            "Configure SQS visibility timeout to 2× max processing time to prevent reprocessing. "
            "Implement dead-letter queue with alerting for messages that fail 3+ times. "
            "Pre-define a scale-out runbook and test it quarterly."
        ),
    },
    "regional_divergence": {
        "stop_bleeding": (
            "1. Reroute traffic away from the degraded region immediately. AWS Route 53: set "
            "health check on the affected endpoint and enable failover routing. GCP: update "
            "Cloud DNS geo-routing policy. Cloudflare: disable the affected data center in "
            "load balancer settings.\n"
            "2. Verify health check sensitivity — ensure your LB is checking the actual app "
            "health endpoint (not just TCP), with a failure threshold of 2 and check interval "
            "of 10s.\n"
            "3. If traffic is not rerouting automatically, manually update your DNS failover "
            "record and reduce TTL to 60s."
        ),
        "prevent_recurrence": (
            "Implement active-active or active-passive failover with pre-tested runbooks. "
            "Run quarterly chaos experiments that fail a full AZ and verify auto-reroute "
            "completes within your RTO. Monitor per-region error rates separately from "
            "aggregate metrics."
        ),
    },
    "hurricane_datacenter": {
        "stop_bleeding": (
            "1. Initiate failover to your hot standby region NOW, before power is lost. "
            "Waiting until the facility goes dark means you lose database sync windows.\n"
            "2. Snapshot all stateful services (RDS: create-db-snapshot, ElastiCache: "
            "create-snapshot) before the event reaches the facility.\n"
            "3. Redirect DNS to your DR region with a 60-second TTL and verify all "
            "health checks pass in the DR region before declaring failover complete."
        ),
        "prevent_recurrence": (
            "All primary facilities should have a documented and tested DR runbook. "
            "Validate your RTO/RPO assumptions annually with a real failover drill. "
            "For hurricane-prone regions, initiate failover when NWS issues a 72-hour "
            "landfall forecast — not after the event begins."
        ),
    },
    "vendor_capacity_crunch": {
        "stop_bleeding": (
            "1. Immediately try a different instance family in the same region "
            "(e.g., if c5.xlarge is exhausted, try c6i.xlarge or m5.xlarge — same vCPU/RAM tier "
            "with different hardware backing).\n"
            "2. If same-region capacity is exhausted, launch instances in an adjacent region "
            "(us-east-1 ↔ us-east-2) and route traffic via your load balancer.\n"
            "3. Contact your AWS/GCP/Azure TAM directly — capacity reservations can sometimes "
            "be unlocked via escalation faster than the console will show availability."
        ),
        "prevent_recurrence": (
            "Purchase 1-year Savings Plans or Reserved Instances for your baseline capacity. "
            "Reserved capacity guarantees launch even during regional shortages. "
            "Add a secondary instance family to your ASG launch template as a fallback. "
            "Monitor InstanceLimitExceeded errors in CloudTrail and alert before they block scaling."
        ),
    },
    "cost_cut_redundancy": {
        "stop_bleeding": (
            "1. If cache is down: add db connection pool limits immediately to prevent "
            "connection exhaustion — PostgreSQL: set max_connections and use PgBouncer in "
            "transaction mode with pool_size = floor(max_connections * 0.8).\n"
            "2. Enable read replicas for read traffic immediately to reduce primary DB load.\n"
            "3. Restore the removed redundancy — re-provision the cache node or standby replica "
            "from the most recent snapshot. Do not restore to production until you have verified "
            "replication lag is under 5 seconds."
        ),
        "prevent_recurrence": (
            "Require a formal Redundancy Impact Assessment for any cost-reduction change that "
            "removes a standby component. Include failure scenario walkthrough in the review. "
            "Set a hard policy: no single-AZ deployments for any service on the critical path."
        ),
    },
    "bgp_route_leak": {
        "stop_bleeding": (
            "1. Contact your upstream provider and the provider where the leak originated — "
            "provide the leaked prefix and the originating ASN. Most providers have an NOC "
            "emergency line that can apply a null route or filter within 15–30 minutes.\n"
            "2. If you control the affected AS: apply an outbound route filter (prefix-list "
            "or AS-path filter) to prevent re-advertisement of the leaked routes.\n"
            "3. Implement RPKI (Route Origin Validation) to cryptographically sign your "
            "prefixes — this is the fastest way to get upstream providers to reject the leak."
        ),
        "prevent_recurrence": (
            "Register all your prefixes in a public ROA (Route Origin Authorization) via ARIN/RIPE. "
            "Enable RPKI on all your BGP sessions. Subscribe to BGPmon or similar alerting "
            "to detect when your prefixes are being announced from unexpected ASNs."
        ),
    },
}


# ── Signal extraction keyword map ─────────────────────────────────────────────
# Maps natural language phrases to structured signal IDs used by diagnose()

_SIGNAL_KEYWORDS: List[Tuple[str, str, str]] = [
    # (keyword_pattern, question_id, option_id)
    # q_user_impact
    (r"\b(slow|latent|sluggish|response time|loading slow)\b",         "q_user_impact", "slow_pages"),
    (r"\b(error|5[0-9][0-9]|failed request|failure rate|failing|fail(?:ed|ing))\b", "q_user_impact", "errors"),
    (r"\b(timeout|timed out|timing out|hanging|hung|intermittent)\b",   "q_user_impact", "timeouts"),
    (r"\b(region|geographic|geo|some users|subset of users|partial)\b", "q_user_impact", "regional"),
    (r"\b(job|queue.*delay|notification.*delay|background.*delay)\b",   "q_user_impact", "jobs_delayed"),
    (r"\b(down|outage|unavailable|complete failure|total)\b",           "q_user_impact", "total_outage"),
    # q_telemetry
    (r"\b(latency|p95|p99|response time)\b",                            "q_telemetry",  "latency_up"),
    (r"\b(error rate|error.*rising|4xx|5xx.*spike)\b",                  "q_telemetry",  "error_rate"),
    (r"\b(timeout rate|timeouts.*increasing|timeouts.*up)\b",           "q_telemetry",  "timeouts_up"),
    (r"\b(retry|retries|retry storm|retry.*high)\b",                    "q_telemetry",  "retry_high"),
    (r"\b(queue.*depth|queue.*growing|backlog|message.*piling)\b",      "q_telemetry",  "queue_grow"),
    (r"\b(cpu|memory|resource.*pressure|saturat)\b",                    "q_telemetry",  "cpu_high"),
    (r"\b(cache.*miss|cache hit.*drop|hit rate.*fall)\b",               "q_telemetry",  "cache_drop"),
    # q_trigger
    (r"\b(deploy|deployment|config change|release|push|rollout)\b",     "q_trigger",    "deploy"),
    (r"\b(traffic spike|load spike|surge|sudden.*traffic)\b",           "q_trigger",    "traffic"),
    # DNS/service-discovery issues are dependency triggers
    (r"\b(dns|service[\s-]?discover|name[\s-]?resolut|resolver|resolv)\b", "q_trigger", "dependency"),
    (r"\b(dependency|dependenc|third.party|external.*service|dependency.*slow|vendor.*issue|provider.*down)\b", "q_trigger", "dependency"),
    (r"\b(hardware|server.*fail|machine.*fail|disk|instance.*fail)\b",  "q_trigger",    "hardware"),
    (r"\b(weather|hurricane|earthquake|storm|seismic|power|flood|sanction|regulation)\b", "q_trigger", "external"),
    # q_structural
    (r"\b(single.*point|one.*service.*everything|no.*backup.*service)\b","q_structural", "single_dep"),
    (r"\b(no.*failover|no.*redundan|single.*region)\b",                  "q_structural", "no_failover"),
    (r"\b(retry.*aggressive|no.*backoff|immediate.*retry)\b",            "q_structural", "bad_retries"),
    (r"\b(auto.?scal.*off|scal.*limit|no.*auto.?scal)\b",               "q_structural", "scale_limited"),
    (r"\b(no.*circuit.*break|circuit.*break.*off|no.*cb)\b",            "q_structural", "no_circuit"),
    (r"\b(cut.*redundan|remov.*standby|cost.*cut.*infra)\b",            "q_structural", "reduced_redun"),
    # q_external
    (r"\b(cost.*cut|budget.*cut|reduc.*spend|layoff)\b",                "q_external",   "cost_cut"),
    (r"\b(understaffed|under.*staff|team.*small|short.*staff)\b",       "q_external",   "understaffed"),
    (r"\b(cloud.*capacity|vendor.*capacity|instance.*limit|aws.*limit)\b","q_external", "vendor_issue"),
    (r"\b(regulation|compliance|data.*sovereig|gdpr|data.*residen)\b",  "q_external",   "regulatory"),
    (r"\b(sanction|geopolit|trade.*war|ban)\b",                         "q_external",   "geo_event"),
]


def _extract_signals_from_text(text: str) -> Dict[str, Any]:
    """
    Map free-form incident description to structured responses dict.
    Returns a dict compatible with diagnose(responses).
    Only populates keys where signal evidence was found.
    """
    lowered = text.lower()
    responses: Dict[str, Any] = {
        "q_user_impact": [],
        "q_telemetry":   [],
        "q_trigger":     "",
        "q_structural":  [],
        "q_external":    [],
    }
    trigger_hit = None

    for pattern, q_id, opt_id in _SIGNAL_KEYWORDS:
        if re.search(pattern, lowered):
            if q_id == "q_trigger":
                # single-select: take first match
                if trigger_hit is None:
                    trigger_hit = opt_id
                    responses["q_trigger"] = opt_id
            else:
                if opt_id not in responses[q_id]:
                    responses[q_id].append(opt_id)

    return responses


def _is_sufficient_for_diagnosis(text: str, extracted: Dict[str, Any]) -> bool:
    """
    Returns True if the free-text message contains enough signal to skip the wizard.
    Threshold: at least 2 distinct question dimensions with evidence.
    """
    filled = sum(
        1 for k in ("q_user_impact", "q_telemetry", "q_structural", "q_external")
        if extracted.get(k)
    )
    if extracted.get("q_trigger"):
        filled += 1
    return filled >= 2 and len(text.split()) >= 12


# ── OpenAI call ───────────────────────────────────────────────────────────────

def _call_openai(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.25,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("PULSEGRID_CHAT_MODEL", "gpt-4.1-mini")
    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_message}]
    for item in (attachments or [])[:3]:
        if not isinstance(item, dict):
            continue
        img = item.get("image_base64")
        if isinstance(img, str) and img.startswith("data:image/"):
            user_content.append({"type": "input_image", "image_url": img})

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user",   "content": user_content},
        ],
        "temperature": temperature,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data.get("output_text"), str) and data["output_text"].strip():
            return data["output_text"].strip()
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    return text.strip()
    except Exception:
        return None
    return None


# ── Unified system prompt ─────────────────────────────────────────────────────

def _build_system_prompt(mode: str, scenario: Optional[str] = None) -> str:
    scenario_list = "\n".join(
        f"  - {k}: {v[:120]}..." for k, v in SCENARIO_SUMMARIES.items() if k != "healthy_baseline"
    )

    base = f"""You are PulseGrid AI — a senior SRE incident intelligence engine, not a generic chatbot.

Your job is to give specific, actionable, technically precise answers about cloud infrastructure incidents.
You do not hedge. You do not ask clarifying questions when you already have enough context. You do not say
"it depends" without immediately explaining what it depends on and what the likely answer is for each case.
If you are uncertain, state what the most probable explanation is and why, then flag what would change the answer.

FRAMEWORK: Every incident follows the PulseGrid 7-Layer Failure Propagation Chain.
CRITICAL: These are NOT OSI networking model layers. Never reference Physical/Data Link/Network/Transport
or any OSI concept. PulseGrid's layers are strictly:
  L0 External Drivers         — Budget pressure, understaffing, launch rush, regulatory change
  L1 Structural Conditions    — Architecture fragility: no failover, SPOF, aggressive retries, no circuit breaker
  L2 Triggering Events        — What started the chain: bad deploy, traffic spike, dependency failure, config error
  L3 Internal Stress Mechanics — How the system amplified the shock: retry storms, queue overflow, connection exhaustion
  L4 Telemetry Warning Signs  — Observable metrics: latency climbing, error rate rising, cache hit rate dropping
  L5 User-Visible Degradation — What customers experience: slow pages, errors, late notifications, regional split
  L6 Business / Mission Impact — Organizational consequence: revenue loss, SLA breach, reputational harm

KNOWN SCENARIOS (you have deep expertise on all of these):
{scenario_list}

STATISTICAL BENCHMARKS (cite these when relevant):
{STAT_BENCHMARKS}

RESPONSE RULES:
1. Answer the question directly in the first sentence. No preamble.
2. Be specific. Name the technology, the metric, the threshold, the command.
3. If someone describes symptoms, map them to a scenario and explain the propagation chain.
4. If someone asks what to do, give numbered steps with real tool-specific commands.
5. If asked about prevention, give infrastructure-level changes, not general advice.
6. Tone: confident SRE, not a help desk. Short paragraphs, no fluff.
"""

    if mode == "diagnostic":
        base += "\nCurrent mode: DIAGNOSTIC. Help the user understand what their telemetry signals mean and what scenario they are likely in."
    else:
        active = scenario or "unknown"
        summary = SCENARIO_SUMMARIES.get(active, "")
        playbook = MITIGATION_PLAYBOOKS.get(active, {})
        stop_bleeding = playbook.get("stop_bleeding", "")
        prevent = playbook.get("prevent_recurrence", "")
        base += f"""
Current mode: SCENARIO ANALYSIS for '{active}'.
Active scenario context: {summary}
Immediate mitigation steps: {stop_bleeding}
Prevention: {prevent}
"""
    return base


# ── Wizard signal pre-extraction ─────────────────────────────────────────────

def extract_signals_for_wizard(text: str) -> Dict[str, Any]:
    """
    Extract signals from free text and return which wizard questions
    are already answered so the frontend can skip them.

    Returns:
        pre_answers  — dict mapping question_id → extracted answer(s)
        skippable    — list of question IDs that don't need to be asked
        is_complete  — True if enough signal exists to skip the wizard entirely
    """
    extracted = _extract_signals_from_text(text)
    is_complete = _is_sufficient_for_diagnosis(text, extracted)

    pre_answers: Dict[str, Any] = {}
    skippable: List[str] = []

    for q_id, val in extracted.items():
        if isinstance(val, list) and val:
            pre_answers[q_id] = val
            skippable.append(q_id)
        elif isinstance(val, str) and val:
            pre_answers[q_id] = val
            skippable.append(q_id)

    return {
        "pre_answers": pre_answers,
        "skippable":   skippable,
        "is_complete": is_complete,
    }


# ── Open-ended (GPT-powered) diagnosis for novel incidents ────────────────────

def open_ended_diagnose(description: str, extracted_signals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Use GPT to generate a full 7-layer chain analysis for any incident,
    not limited to the 13 hardcoded scenarios. Falls back gracefully if
    OpenAI is unavailable.

    Returns a result dict in the same format as chain.diagnose().
    """
    from .chain import LAYERS

    sys_prompt = _build_system_prompt("diagnostic")
    signals_summary = ", ".join(
        f"{k}={v}" for k, v in extracted_signals.items() if v and v != [] and v != ""
    )

    user_prompt = (
        f"Incident description: {description}\n\n"
        f"Extracted signals: {signals_summary or 'none extracted — use the description directly'}\n\n"
        f"Analyze this incident using the 7-layer Failure Propagation Chain.\n"
        f"Return ONLY valid JSON with this exact structure (no markdown, no code blocks):\n"
        f"{{\n"
        f'  "incident_name": "short descriptive name (3-5 words, no hyphens)",\n'
        f'  "risk_score": 0.0,\n'
        f'  "risk_state": "healthy|degraded|critical|cascading",\n'
        f'  "summary": "2-3 sentences: what is happening, why, what breaks next",\n'
        f'  "chain": {{\n'
        f'    "layer_0": {{"factors": ["..."], "active": true}},\n'
        f'    "layer_1": {{"factors": ["..."], "active": true}},\n'
        f'    "layer_2": {{"factors": ["..."], "active": true}},\n'
        f'    "layer_3": {{"factors": ["..."], "active": true}},\n'
        f'    "layer_4": {{"factors": ["..."], "active": true}},\n'
        f'    "layer_5": {{"factors": ["..."], "active": true}},\n'
        f'    "layer_6": {{"factors": ["..."], "active": true}}\n'
        f'  }},\n'
        f'  "mitigation": {{\n'
        f'    "now": ["step 1", "step 2", "step 3"],\n'
        f'    "next": ["next 1", "next 2"],\n'
        f'    "prevent": ["prevent 1", "prevent 2"]\n'
        f'  }}\n'
        f"}}\n\n"
        f"Fill each layer with real, specific factors from the incident description. "
        f"Use empty arrays only if a layer truly has no involvement. "
        f"risk_score should be 0.0-1.0 (0.8+ = cascading, 0.6-0.8 = critical, 0.4-0.6 = degraded, <0.4 = low)."
    )

    raw = _call_openai(sys_prompt, user_prompt, temperature=0.15)
    if not raw:
        return None

    try:
        clean = raw.strip()
        # Strip markdown fences if present
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:] if lines[0].startswith("```") else lines)
            if clean.endswith("```"):
                clean = clean[:-3]
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return None

    # Build chain in the same format chain.diagnose() uses
    chain: Dict[str, Any] = {}
    for i in range(7):
        lk = f"layer_{i}"
        ld = data.get("chain", {}).get(lk, {})
        chain[lk] = {
            "layer":   LAYERS[i],
            "factors": ld.get("factors", []),
            "active":  ld.get("active", bool(ld.get("factors"))),
        }

    raw_risk = float(data.get("risk_score", 0.5))
    risk_score = round(min(1.0, max(0.0, raw_risk)), 3)
    risk_state = data.get("risk_state", "degraded")

    from .scoring import STATE_COLORS
    risk_color = STATE_COLORS.get(risk_state, "#fb923c")

    # Normalize mitigation to the format renderResults() expects
    mit_raw = data.get("mitigation", {})
    mitigation = {
        "now":     [{"text": s, "how": ""} for s in mit_raw.get("now", [])],
        "next":    [{"text": s, "how": ""} for s in mit_raw.get("next", [])],
        "prevent": [{"text": s, "how": ""} for s in mit_raw.get("prevent", [])],
    }

    incident_name = data.get("incident_name", "custom_incident")
    scenario_id   = incident_name.lower().replace(" ", "_").replace("-", "_")[:40]

    return {
        "matched_scenario":  scenario_id,
        "scenario_label":    incident_name,
        "match_confidence":  12,
        "risk_score":        risk_score,
        "risk_state":        risk_state,
        "risk_color":        risk_color,
        "chain":             chain,
        "summary":           data.get("summary", ""),
        "mitigation":        mitigation,
        "signals_detected":  extracted_signals,
        "is_open_ended":     True,
    }


# ── Free-text extraction + diagnosis ─────────────────────────────────────────

def extract_and_diagnose(message: str) -> Optional[Dict[str, Any]]:
    """
    If the message is a sufficient incident description, extract signals,
    run diagnose(), and return the full result dict.

    When the structured scenario-matching confidence is low (novel incident
    that doesn't fit the 13 known patterns), falls back to open_ended_diagnose()
    which uses GPT to produce a fully custom 7-layer analysis.

    Returns None if the message is not a sufficient incident description.
    """
    extracted = _extract_signals_from_text(message)
    if not _is_sufficient_for_diagnosis(message, extracted):
        return None

    diag = diagnose(extracted)

    # Low confidence: novel incident — try GPT-powered open-ended analysis
    LOW_CONFIDENCE_THRESHOLD = 6
    if diag["match_confidence"] < LOW_CONFIDENCE_THRESHOLD or diag["matched_scenario"] == "healthy_baseline":
        oe = open_ended_diagnose(message, diag.get("signals_detected", {}))
        if oe:
            # Generate narrative from GPT using the open-ended result
            sys_p = _build_system_prompt("diagnostic")
            narr = _call_openai(sys_p, (
                f"Incident: {message}\n\n"
                f"Chain analysis complete. Incident name: {oe['scenario_label']}. "
                f"Risk: {round(oe['risk_score']*100)}% ({oe['risk_state']}). "
                f"Summary: {oe['summary']}\n\n"
                f"Write a 2-paragraph incident brief. First paragraph: what is happening "
                f"and the root cause chain. Second paragraph: what to do in the next 5 minutes. "
                f"Be specific. No hedging. No hyphens."
            ), temperature=0.2) or oe["summary"]
            return {
                "full_result":  oe,
                "narrative":    narr,
                "scenario":     oe["matched_scenario"],
                "risk_score":   oe["risk_score"],
                "risk_state":   oe["risk_state"],
            }

    # If score is too low to match anything meaningful, return None
    if diag["matched_scenario"] == "healthy_baseline" and diag["match_confidence"] < 2:
        return None

    scenario = diag["matched_scenario"]
    summary = SCENARIO_SUMMARIES.get(scenario, "")
    playbook = MITIGATION_PLAYBOOKS.get(scenario, {})

    # Use GPT to write a sharp narrative if available
    sys_prompt = _build_system_prompt("scenario", scenario)
    signals_found = ", ".join(
        f"{k}={v}" for k, v in diag["signals_detected"].items() if v > 0
    )
    user_prompt = (
        f"Incident description: {message}\n\n"
        f"Signals extracted: {signals_found}\n"
        f"Matched scenario: {scenario} (confidence {diag['match_confidence']}, "
        f"risk {round(diag['risk_score']*100)}%)\n\n"
        f"Write a 3-paragraph incident brief:\n"
        f"1. What is happening and why (root cause chain)\n"
        f"2. What breaks next if nothing is done (blast radius)\n"
        f"3. The single most important action to take RIGHT NOW, with a specific command or config change\n"
        f"Be direct, specific, authoritative. No hedging."
    )
    narrative = _call_openai(sys_prompt, user_prompt, temperature=0.2)

    if not narrative:
        # Build fallback narrative from chain data
        stop_bleeding = playbook.get("stop_bleeding", "")
        narrative = (
            f"Your incident matches the {scenario.replace('_', ' ')} pattern "
            f"at {round(diag['risk_score']*100)}% composite risk ({diag['risk_state']} state). "
            f"{summary} "
            f"Immediate action: {stop_bleeding[:300] if stop_bleeding else 'Isolate the failing dependency and reduce retry pressure.'}"
        )

    return {
        "full_result":  diag,
        "narrative":    narrative,
        "scenario":     scenario,
        "risk_score":   diag["risk_score"],
        "risk_state":   diag["risk_state"],
    }


# ── Fallback response builders ────────────────────────────────────────────────

def _fallback_diagnostic(message: str, responses: Dict[str, Any], step: Optional[int], current_question: Optional[str]) -> str:
    msg = (message or "").strip().lower()
    scenario_guess = None

    # Off-topic guardrail: if message has no infrastructure signal, reject cleanly
    _INFRA_TERMS = [
        'latency', 'error', 'timeout', 'deploy', 'service', 'server', 'database', 'cache',
        'queue', 'worker', 'cpu', 'memory', 'network', 'api', 'load', 'traffic', 'request',
        'retry', 'circuit', 'failover', 'region', 'instance', 'pod', 'container', 'dns',
        'http', '5xx', '4xx', 'spike', 'degraded', 'outage', 'incident', 'alert', 'monitor',
        'auth', 'login', 'checkout', 'payment', 'sla', 'throughput', 'bandwidth', 'packet',
        'downtime', 'replication', 'shard', 'replica', 'cluster', 'node', 'endpoint',
        'latent', 'slow', 'down', 'fail', 'crash', 'hang', 'stuck', 'broke', 'broken',
        'notification', 'job', 'backlog', 'saturat', 'exhaust', 'overflow', 'cascade',
    ]
    has_infra_signal = any(term in msg for term in _INFRA_TERMS)
    if not has_infra_signal and len(msg.split()) >= 4:
        return (
            "That doesn't sound like an infrastructure symptom. "
            "Describe user impact, a telemetry signal, a recent change, or a dependency issue "
            "— and I'll map it to the failure chain."
        )

    # Try to extract signals and get a tentative read
    extracted = _extract_signals_from_text(message)
    if any(extracted.get(k) for k in extracted):
        tentative = diagnose({**responses, **{k: v for k, v in extracted.items() if v}})
        scenario_guess = tentative.get("matched_scenario")
        risk_pct = round((tentative.get("risk_score", 0) or 0) * 100)
        if scenario_guess and scenario_guess != "healthy_baseline":
            scenario_label = scenario_guess.replace("_", " ")
            summary = SCENARIO_SUMMARIES.get(scenario_guess, "")[:200]
            return (
                f"Based on what you've described, this is trending toward a {scenario_label} pattern "
                f"at ~{risk_pct}% risk. {summary} "
                + (f"Keep answering: {current_question}" if current_question else
                   "Continue through the questions to confirm and get the full analysis.")
            )

    # Glossary terms
    glossary = {
        "circuit breaker": "A circuit breaker is an automatic gate that stops calls to a failing dependency. When error rate or latency exceeds a threshold, the breaker opens and short-circuits requests — protecting your thread pools from filling with waiting requests to a service that cannot respond.",
        "retry storm": "A retry storm is when clients retry failed requests faster than the dependency can recover. Each retry adds load to an already-failing service, causing exponential amplification. Without a circuit breaker and backoff, a 10% failure can become a 100% outage in under 3 minutes.",
        "blast radius": "Blast radius is the set of services that will degrade after a primary failure. PulseGrid propagates risk through the dependency graph — direct dependents absorb 60–80% of the degradation signal, and their dependents absorb 20–40%.",
        "latency": "Latency is end-to-end request time. Rising p95/p99 latency before error rates climb is a leading indicator — it means the dependency is slowing down but not yet failing hard. Act on latency signals before error rate confirms the failure.",
        "timeout": "Timeouts fire when a service waits too long for a response and gives up. Timeout clusters against the same dependency almost always point to a single upstream — check which service all timed-out calls have in common.",
        "queue": "Queue depth growth means consumers cannot drain faster than producers enqueue. Calculate your drain deficit: (ingestion_rate - processing_rate) × time = depth. Scale consumers by at least that ratio to stop depth from growing.",
    }
    for term, explanation in glossary.items():
        if term in msg:
            q_suffix = f" Current question: {current_question}" if current_question else ""
            return explanation + q_suffix

    if any(k in msg for k in ["what do you know", "so far", "summary", "tentative", "what have"]):
        from .chain import diagnose as _diagnose
        tentative = _diagnose(responses or {})
        scenario = tentative.get("matched_scenario", "healthy_baseline").replace("_", " ")
        risk = round((tentative.get("risk_score", 0) or 0) * 100)
        sigs = tentative.get("signals_detected", {})
        top_sigs = sorted(sigs.items(), key=lambda x: x[1], reverse=True)[:3]
        sig_str = ", ".join(f"{s}={v}" for s, v in top_sigs) if top_sigs else "none yet"
        return (
            f"Current read: trending {scenario} at ~{risk}% risk. "
            f"Strongest signals: {sig_str}. "
            + (f"Next: {current_question}" if current_question else "A few more answers will lock the diagnosis.")
        )

    q_suffix = f" Answer the current question to continue: {current_question}" if current_question else ""
    return (
        "I can clarify terms, explain what the current signals mean, or summarize the diagnosis so far. "
        "Ask me about any metric, failure mode, or infrastructure concept — or describe what you're seeing "
        "and I'll map it to a scenario." + q_suffix
    )


def _fallback_scenario(message: str, scenario: str, scenario_context: Dict[str, Any], scenario_state: Optional[Dict[str, Any]]) -> str:
    msg = (message or "").strip().lower()
    recs = (scenario_state or {}).get("recommendations", {})
    sys_state = (scenario_state or {}).get("system_state", {})
    summary = SCENARIO_SUMMARIES.get(scenario, scenario_context.get("summary", ""))

    if any(k in msg for k in ["what happened", "cause", "why", "root cause", "explain"]):
        return summary or f"This scenario models {scenario.replace('_', ' ')}."

    if any(k in msg for k in ["risk", "score", "severity", "state", "how bad"]):
        state = sys_state.get("state", "unknown")
        score = round((sys_state.get("score", 0) or 0) * 100)
        return (
            f"System state: {state} at {score}% composite risk in the {scenario.replace('_', ' ')} scenario. "
            f"This means {_risk_state_meaning(state, score)}."
        )

    if any(k in msg for k in ["what do i do", "action", "mitigation", "fix", "next step", "how do i fix", "stop this"]):
        playbook = MITIGATION_PLAYBOOKS.get(scenario, {})
        stop = playbook.get("stop_bleeding", "")
        if stop:
            return f"Stop-the-bleeding steps for {scenario.replace('_', ' ')}:\n{stop}"
        immediate = recs.get("immediate_actions", [])[:3]
        if immediate:
            return "Immediate actions: " + "; ".join(immediate)
        return "No concrete playbook loaded for this scenario yet."

    if any(k in msg for k in ["prevent", "future", "recurrence", "postmortem", "long term"]):
        playbook = MITIGATION_PLAYBOOKS.get(scenario, {})
        prevent = playbook.get("prevent_recurrence", "")
        if prevent:
            return prevent
        optimize = recs.get("optimization_opportunities", [])[:3]
        return ("Prevention steps: " + "; ".join(optimize)) if optimize else "No prevention data loaded."

    if any(k in msg for k in ["notify", "page", "who", "escalat", "tell"]):
        return (
            "Notify: (1) owner of the primary failing service, (2) SRE or incident lead, "
            "(3) customer communications if users are impacted, (4) platform/infra leadership "
            "if this is a regional or datacenter-level event. For regulated industries, pull "
            "in compliance before making any public statements."
        )

    if any(k in msg for k in ["how long", "mttr", "recover", "resolution time"]):
        return (
            f"Median MTTR for a {scenario.replace('_', ' ')} incident is 2–5 hours based on "
            f"PagerDuty data (n=15,000+). Fastest recovery path: isolate the trigger first, "
            f"then drain or reroute load. Most time is lost in detection and coordination, "
            f"not in the actual fix. If you have the playbook loaded and the right people "
            f"notified, MTTR drops to 30–90 minutes for well-practiced teams."
        )

    return (
        f"Active scenario: {scenario.replace('_', ' ')}. {summary[:200]} "
        f"Ask me about root cause, blast radius, mitigation steps, prevention, who to notify, "
        f"or expected recovery time."
    )


def _risk_state_meaning(state: str, score: int) -> str:
    meanings = {
        "critical": f"multiple services are degraded and cascading failure is in progress — every minute of inaction costs blast radius expansion",
        "high":     f"a primary service is failing and adjacent services are absorbing risk — act before propagation locks in",
        "medium":   f"early warning signals are active — the window to prevent escalation is open",
        "low":      f"minor anomalies detected, likely self-resolving but worth watching",
        "healthy":  f"all services nominal",
    }
    return meanings.get(state, f"risk level is {score}%, investigate further")


# ── Main entry point ──────────────────────────────────────────────────────────

def answer_chat(
    message: str,
    mode: str = "scenario",
    scenario: Optional[str] = None,
    responses: Optional[Dict[str, Any]] = None,
    step: Optional[int] = None,
    current_question: Optional[str] = None,
    scenario_context: Optional[Dict[str, Any]] = None,
    scenario_state: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Unified chat brain for both diagnostic and scenario modes.

    Returns a plain string reply. Free-text diagnosis bypass is handled
    by extract_and_diagnose() which is called separately from the API layer
    before this function when mode == "diagnostic".
    """
    responses        = responses or {}
    scenario_context = scenario_context or {}

    sys_prompt  = _build_system_prompt(mode, scenario)

    if mode == "diagnostic":
        # Build rich context from current diagnostic state
        q = current_question or ""
        if not q and step is not None:
            try:
                idx = int(step)
                if 0 <= idx < len(QUESTIONS):
                    q = QUESTIONS[idx]["text"]
            except Exception:
                pass

        # Tentative scenario from current answers
        tentative = diagnose(responses) if responses else {}
        t_scenario = tentative.get("matched_scenario", "unknown")
        t_risk     = round((tentative.get("risk_score", 0) or 0) * 100)
        t_sigs     = tentative.get("signals_detected", {})
        top_sigs   = sorted(t_sigs.items(), key=lambda x: x[1], reverse=True)[:4]
        sig_str    = ", ".join(f"{s}={v}" for s, v in top_sigs) if top_sigs else "none"

        user_prompt = (
            f"Diagnostic step: {step} | Active question: {q}\n"
            f"Signals so far: {sig_str}\n"
            f"Tentative scenario: {t_scenario} at {t_risk}% risk\n"
            f"User message: {message}"
        )
        live = _call_openai(sys_prompt, user_prompt, attachments=attachments)
        return live or _fallback_diagnostic(message, responses, step, current_question)

    # Scenario mode — rich context injection
    active_scenario = scenario or "unknown"
    s_state   = (scenario_state or {}).get("system_state", {})
    s_recs    = (scenario_state or {}).get("recommendations", {})
    s_blast   = (scenario_state or {}).get("blast_radius", [])

    blast_summary = ""
    if s_blast:
        top_affected = sorted(s_blast, key=lambda x: x.get("score", 0), reverse=True)[:4]
        blast_summary = ", ".join(
            f"{x['service_id']} ({round(x.get('score',0)*100)}%)" for x in top_affected
        )

    immediate = s_recs.get("immediate_actions", [])[:3]
    optimize  = s_recs.get("optimization_opportunities", [])[:2]

    user_prompt = (
        f"Scenario: {active_scenario}\n"
        f"System state: {s_state.get('state', 'unknown')} at {round((s_state.get('score',0) or 0)*100)}% risk\n"
        f"Most affected services: {blast_summary or 'not available'}\n"
        f"Immediate actions: {'; '.join(immediate) if immediate else 'none loaded'}\n"
        f"Optimization actions: {'; '.join(optimize) if optimize else 'none loaded'}\n"
        f"Scenario context: {scenario_context.get('summary', '')[:300]}\n"
        f"User message: {message}"
    )
    live = _call_openai(sys_prompt, user_prompt, attachments=attachments)
    return live or _fallback_scenario(message, active_scenario, scenario_context, scenario_state)
