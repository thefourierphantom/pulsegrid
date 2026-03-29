# simulator/scenarios.py
# PulseGrid scenario definitions — 12 scenarios across 5 real-world categories
#
# Each scenario defines how telemetry evolves over TOTAL_STEPS time steps.
# Each scenario also carries "context intelligence" — the pre-signal world
# conditions (physical, economic, geopolitical, infrastructure) that drive
# the observed telemetry degradation.
#
# This is the core thesis: cloud infrastructure failure is not born in software.
# It is born in the physical world — hardware scarcity, power grids, undersea
# cables, regulatory mandates, economic pressure — and PulseGrid surfaces these
# causal factors before your monitoring tools even notice the metrics move.

import math
import random

TOTAL_STEPS = 32
NOISE_SEED  = 42

# ── Healthy baseline ──────────────────────────────────────────────────────────
HEALTHY_BASE = {
    "frontend":    {"latency_ms": 38,  "error_rate": 0.002, "retry_rate": 0.008, "timeout_rate": 0.001, "cpu_util": 0.18, "connection_count": 45},
    "api_gateway": {"latency_ms": 42,  "error_rate": 0.003, "retry_rate": 0.010, "timeout_rate": 0.001, "cpu_util": 0.22, "connection_count": 60},
    "auth":        {"latency_ms": 28,  "error_rate": 0.001, "retry_rate": 0.005, "timeout_rate": 0.000, "cpu_util": 0.14, "connection_count": 35},
    "cache":       {"latency_ms": 8,   "error_rate": 0.000, "retry_rate": 0.002, "timeout_rate": 0.000, "cpu_util": 0.10, "connection_count": 80,  "cache_hit_rate": 0.96},
    "queue":       {"latency_ms": 12,  "error_rate": 0.001, "retry_rate": 0.003, "timeout_rate": 0.000, "cpu_util": 0.12, "connection_count": 20,  "queue_depth": 8},
    "worker":      {"latency_ms": 95,  "error_rate": 0.002, "retry_rate": 0.007, "timeout_rate": 0.001, "cpu_util": 0.35, "connection_count": 28},
    "database":    {"latency_ms": 18,  "error_rate": 0.001, "retry_rate": 0.004, "timeout_rate": 0.000, "cpu_util": 0.28, "connection_count": 55},
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _noise(rng, scale=1.0):
    return rng.gauss(0, scale)

def _lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))

def _sigmoid(x, center=0.5, steepness=8):
    return 1.0 / (1.0 + math.exp(-steepness * (x - center)))

def _build_step(base, overrides, rng, noise_scale=0.04):
    result = {}
    for key, base_val in base.items():
        override = overrides.get(key, base_val)
        noise = _noise(rng, abs(base_val) * noise_scale + 0.001)
        if key in ("error_rate", "retry_rate", "timeout_rate"):
            result[key] = max(0.0, round(override + noise, 5))
        elif key == "cache_hit_rate":
            result[key] = max(0.0, min(1.0, round(override + noise * 0.3, 4)))
        elif key == "queue_depth":
            result[key] = max(0, round(override + noise * 3))
        elif key == "cpu_util":
            result[key] = max(0.0, min(1.0, round(override + noise, 4)))
        else:
            result[key] = max(1, round(override + noise * 2, 1))
    return result


# ════════════════════════════════════════════════════════════════════════════
# CATEGORY 1: HEALTHY BASELINE
# ════════════════════════════════════════════════════════════════════════════

def scenario_healthy(rng):
    history = []
    for step in range(TOTAL_STEPS):
        frame = {}
        for svc, base in HEALTHY_BASE.items():
            frame[svc] = _build_step(base, {}, rng, noise_scale=0.03)
        history.append(frame)
    return history


# ════════════════════════════════════════════════════════════════════════════
# CATEGORY 2: NATURAL DISASTER & ENVIRONMENTAL
# ════════════════════════════════════════════════════════════════════════════

def scenario_hurricane_datacenter(rng):
    """
    A Category 3 hurricane makes landfall near a major cloud region.
    Power fluctuations cause thermal stress. Cooling systems are overloaded.
    Network peering points on coastal fiber routes degrade.
    Timeline: thermal throttling → network instability → error cascade.
    """
    history = []
    for step in range(TOTAL_STEPS):
        # Phase 1: thermal stress (power fluctuation → cpu throttling)
        t1 = max(0.0, (step - 7) / 12)
        s1 = _sigmoid(t1, 0.40, 6)

        # Phase 2: network degradation (coastal fiber routes deteriorate)
        t2 = max(0.0, (step - 16) / 10)
        s2 = _sigmoid(t2, 0.45, 7)

        frame = {}

        # All compute services throttle under thermal stress
        frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
            "cpu_util":     _lerp(0.35, 0.97, s1),
            "latency_ms":   _lerp(95,  1100,  s1),
            "error_rate":   _lerp(0.002, 0.10, s2),
            "timeout_rate": _lerp(0.001, 0.08, s2),
        }, rng)

        frame["database"] = _build_step(HEALTHY_BASE["database"], {
            "cpu_util":         _lerp(0.28, 0.93, s1),
            "latency_ms":       _lerp(18,   720,  s1),
            "connection_count": _lerp(55,   460,  s1),
            "error_rate":       _lerp(0.001, 0.07, s2),
        }, rng)

        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":   _lerp(42,   680,  s1),
            "cpu_util":     _lerp(0.22, 0.84, s1),
            "timeout_rate": _lerp(0.001, 0.11, s2),
            "error_rate":   _lerp(0.003, 0.09, s2),
        }, rng)

        frame["auth"] = _build_step(HEALTHY_BASE["auth"], {
            "latency_ms": _lerp(28, 460, s1),
            "cpu_util":   _lerp(0.14, 0.72, s1),
        }, rng)

        fe_t = max(0.0, (step - 12) / 14)
        fe_s = _sigmoid(fe_t, 0.4, 5)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
            "latency_ms":  _lerp(38,   820,  fe_s),
            "error_rate":  _lerp(0.002, 0.07, s2),
        }, rng)

        frame["cache"] = _build_step(HEALTHY_BASE["cache"], {
            "cache_hit_rate": _lerp(0.96, 0.71, s1),
            "cpu_util":       _lerp(0.10, 0.58, s1),
        }, rng)

        frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
            "queue_depth": _lerp(8,   180,  s1),
            "cpu_util":    _lerp(0.12, 0.51, s1),
        }, rng)

        history.append(frame)
    return history


def scenario_power_grid_brownout(rng):
    """
    Regional power authority issues a brownout notice — voltage reduced 8%.
    Servers throttle to prevent hardware damage.
    All services slow uniformly as thermal limits are approached.
    Timeline: uniform cpu throttle → latency drift → queue builds → workers fall behind.
    """
    history = []
    for step in range(TOTAL_STEPS):
        t = max(0.0, (step - 6) / 22)
        s = _sigmoid(t, 0.40, 6)

        frame = {}
        for svc_id, base in HEALTHY_BASE.items():
            cpu_stress = _lerp(base["cpu_util"], min(0.92, base["cpu_util"] * 3.1), s)
            lat_stress = _lerp(base["latency_ms"], base["latency_ms"] * 7.5, s)
            overrides = {"cpu_util": cpu_stress, "latency_ms": lat_stress}

            if svc_id == "queue":
                overrides["queue_depth"] = _lerp(8, 380, s)
            if svc_id == "cache":
                overrides["cache_hit_rate"] = _lerp(0.96, 0.68, s)
            if svc_id in ("worker", "database"):
                overrides["error_rate"] = _lerp(base["error_rate"], 0.06, s)

            frame[svc_id] = _build_step(base, overrides, rng)

        history.append(frame)
    return history


def scenario_seismic_failure(rng):
    """
    A 6.2 magnitude earthquake strikes a subregion hosting the database
    and worker cluster. Power is immediately lost. No graceful shutdown.
    Timeline: sudden step-change failure at onset → cascade to dependent services.
    """
    history = []
    ONSET = 10
    for step in range(TOTAL_STEPS):
        frame = {}

        if step < ONSET:
            # Normal operations — no warning
            for svc, base in HEALTHY_BASE.items():
                frame[svc] = _build_step(base, {}, rng, noise_scale=0.025)
        else:
            # Step-change at seismic event
            t = min(1.0, (step - ONSET) / 8)
            s = _sigmoid(t, 0.25, 10)  # rapid onset

            # Datacenter in seismic zone: database + worker go dark
            frame["database"] = _build_step(HEALTHY_BASE["database"], {
                "error_rate":   _lerp(0.001, 0.72, s),
                "latency_ms":   _lerp(18,   2800, s),
                "cpu_util":     _lerp(0.28,  0.99, s),
                "connection_count": _lerp(55, 5, s),  # connections drop
            }, rng)

            frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
                "error_rate":   _lerp(0.002, 0.68, s),
                "latency_ms":   _lerp(95,   3200, s),
                "cpu_util":     _lerp(0.35,  0.98, s),
                "timeout_rate": _lerp(0.001, 0.41, s),
            }, rng)

            # Cache also in that rack — partial failure
            frame["cache"] = _build_step(HEALTHY_BASE["cache"], {
                "cache_hit_rate": _lerp(0.96, 0.18, s),
                "error_rate":     _lerp(0.00, 0.35, s),
            }, rng)

            # Downstream services cascade
            t2 = min(1.0, (step - ONSET - 2) / 10)
            s2 = _sigmoid(max(0, t2), 0.35, 8)

            frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
                "error_rate":   _lerp(0.003, 0.45, s2),
                "latency_ms":   _lerp(42,   1800, s2),
                "retry_rate":   _lerp(0.010, 0.38, s2),
                "timeout_rate": _lerp(0.001, 0.22, s2),
            }, rng)

            frame["auth"] = _build_step(HEALTHY_BASE["auth"], {
                "latency_ms":   _lerp(28, 640, s2),
                "error_rate":   _lerp(0.001, 0.12, s2),
            }, rng)

            frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
                "queue_depth": _lerp(8, 600, s2),
            }, rng)

            frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
                "error_rate":  _lerp(0.002, 0.32, s2),
                "latency_ms":  _lerp(38,   2100, s2),
            }, rng)

        history.append(frame)
    return history


# ════════════════════════════════════════════════════════════════════════════
# CATEGORY 3: INFRASTRUCTURE & NETWORK FAILURE
# ════════════════════════════════════════════════════════════════════════════

def scenario_retry_storm(rng):
    """Auth service begins failing. Clients retry aggressively. API gateway overloads."""
    history = []
    for step in range(TOTAL_STEPS):
        t = max(0.0, (step - 8) / 18)
        sig = _sigmoid(t, center=0.4, steepness=7)
        frame = {}

        frame["auth"] = _build_step(HEALTHY_BASE["auth"], {
            "error_rate":   _lerp(0.001, 0.24, sig),
            "latency_ms":   _lerp(28,    520,  sig),
            "retry_rate":   _lerp(0.005, 0.28, sig),
            "timeout_rate": _lerp(0.000, 0.10, sig),
            "cpu_util":     _lerp(0.14,  0.82, sig),
        }, rng)

        lag_t = max(0.0, (step - 11) / 16)
        lag_sig = _sigmoid(lag_t, center=0.4, steepness=6)
        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "error_rate":        _lerp(0.003, 0.12, lag_sig),
            "latency_ms":        _lerp(42,    680,  lag_sig),
            "retry_rate":        _lerp(0.010, 0.35, lag_sig),
            "timeout_rate":      _lerp(0.001, 0.08, lag_sig),
            "cpu_util":          _lerp(0.22,  0.89, lag_sig),
            "connection_count":  _lerp(60,    420,  lag_sig),
        }, rng)

        fe_t = max(0.0, (step - 14) / 14)
        fe_sig = _sigmoid(fe_t, center=0.4, steepness=5)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
            "latency_ms":  _lerp(38,    740,  fe_sig),
            "error_rate":  _lerp(0.002, 0.06, fe_sig),
        }, rng)

        for svc in ("cache", "queue", "worker", "database"):
            frame[svc] = _build_step(HEALTHY_BASE[svc], {}, rng)

        history.append(frame)
    return history


def scenario_dns_degradation(rng):
    """DNS resolver degrades → timeout clustering → latency drift → error onset."""
    history = []
    for step in range(TOTAL_STEPS):
        t = max(0.0, (step - 6) / 20)
        sig = _sigmoid(t, center=0.35, steepness=6)
        frame = {}

        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":   _lerp(42,   890, sig),
            "timeout_rate": _lerp(0.001, 0.14, sig),
            "error_rate":   _lerp(0.003, 0.09, sig),
            "retry_rate":   _lerp(0.010, 0.18, sig),
            "cpu_util":     _lerp(0.22,  0.71, sig),
        }, rng)

        frame["auth"] = _build_step(HEALTHY_BASE["auth"], {
            "latency_ms":   _lerp(28,  640, sig),
            "timeout_rate": _lerp(0.000, 0.10, sig),
            "error_rate":   _lerp(0.001, 0.06, sig),
        }, rng)

        fe_t = max(0.0, (step - 10) / 16)
        fe_sig = _sigmoid(fe_t, center=0.4, steepness=5)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
            "latency_ms":  _lerp(38,   920, fe_sig),
            "error_rate":  _lerp(0.002, 0.07, fe_sig),
        }, rng)

        for svc in ("cache", "queue", "worker", "database"):
            frame[svc] = _build_step(HEALTHY_BASE[svc], {}, rng)

        history.append(frame)
    return history


def scenario_bgp_route_leak(rng):
    """
    A misconfigured BGP peer announces incorrect routes globally.
    Traffic is misdirected to a wrong AS — packets take wrong paths or are dropped.
    Latency spikes globally. Timeouts cluster. Error rate slowly climbs.
    Timeline: latency spike → timeout clustering → error rate → partial recovery.
    """
    history = []
    for step in range(TOTAL_STEPS):
        # BGP leak onset: sudden, then partial recovery mid-scenario
        t_onset = max(0.0, (step - 5) / 14)
        s_onset = _sigmoid(t_onset, 0.35, 8)

        # Partial recovery at step 22 as BGP filters are applied
        t_recov = max(0.0, (step - 22) / 8)
        s_recov = _sigmoid(t_recov, 0.5, 7)

        effective = max(0.0, s_onset - s_recov * 0.65)  # partial recovery

        frame = {}

        # External-facing services hit hardest (misdirected external traffic)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
            "latency_ms":   _lerp(38,   1800, effective),
            "timeout_rate": _lerp(0.001, 0.18, effective),
            "error_rate":   _lerp(0.002, 0.14, effective),
        }, rng)

        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":   _lerp(42,   1600, effective),
            "timeout_rate": _lerp(0.001, 0.15, effective),
            "error_rate":   _lerp(0.003, 0.12, effective),
            "retry_rate":   _lerp(0.010, 0.22, effective),
        }, rng)

        # Internal services less affected (traffic stays on internal routing)
        frame["auth"] = _build_step(HEALTHY_BASE["auth"], {
            "latency_ms": _lerp(28, 320, effective * 0.6),
        }, rng)

        for svc in ("cache", "queue", "worker", "database"):
            frame[svc] = _build_step(HEALTHY_BASE[svc], {
                "latency_ms": _lerp(HEALTHY_BASE[svc]["latency_ms"],
                                    HEALTHY_BASE[svc]["latency_ms"] * 2.8,
                                    effective * 0.4),
            }, rng)

        history.append(frame)
    return history


# ════════════════════════════════════════════════════════════════════════════
# CATEGORY 4: CASCADE FAILURE PATTERNS
# ════════════════════════════════════════════════════════════════════════════

def scenario_queue_backlog(rng):
    """Message ingestion rate exceeds worker capacity → queue depth grows → cascading load."""
    history = []
    for step in range(TOTAL_STEPS):
        t = max(0.0, (step - 7) / 20)
        sig = _sigmoid(t, center=0.4, steepness=7)
        frame = {}

        frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
            "queue_depth": _lerp(8,   480, sig),
            "cpu_util":    _lerp(0.12, 0.55, sig),
            "latency_ms":  _lerp(12,  180,  sig),
        }, rng)

        w_t = max(0.0, (step - 9) / 18)
        w_sig = _sigmoid(w_t, center=0.4, steepness=6)
        frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
            "cpu_util":     _lerp(0.35, 0.96, w_sig),
            "latency_ms":   _lerp(95,   820,  w_sig),
            "error_rate":   _lerp(0.002, 0.08, w_sig),
            "connection_count": _lerp(28, 360, w_sig),
        }, rng)

        db_t = max(0.0, (step - 12) / 15)
        db_sig = _sigmoid(db_t, center=0.4, steepness=5)
        frame["database"] = _build_step(HEALTHY_BASE["database"], {
            "latency_ms":    _lerp(18,   540,  db_sig),
            "cpu_util":      _lerp(0.28,  0.88, db_sig),
            "connection_count": _lerp(55, 450,  db_sig),
            "error_rate":    _lerp(0.001, 0.05, db_sig),
        }, rng)

        api_t = max(0.0, (step - 15) / 12)
        api_sig = _sigmoid(api_t, center=0.4, steepness=5)
        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":  _lerp(42,   690,  api_sig),
            "error_rate":  _lerp(0.003, 0.04, api_sig),
        }, rng)

        frame["cache"] = _build_step(HEALTHY_BASE["cache"], {
            "cache_hit_rate": _lerp(0.96, 0.61, sig),
            "cpu_util":       _lerp(0.10, 0.45, sig),
        }, rng)

        frame["auth"]     = _build_step(HEALTHY_BASE["auth"], {}, rng)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"],
            {"latency_ms": _lerp(38, 580, api_sig)}, rng)

        history.append(frame)
    return history


def scenario_regional_divergence(rng):
    """One region's worker pool begins failing → intermittent errors → replication lag."""
    history = []
    for step in range(TOTAL_STEPS):
        t = max(0.0, (step - 8) / 20)
        sig = _sigmoid(t, center=0.45, steepness=6)
        frame = {}

        frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
            "error_rate":   _lerp(0.002, 0.18, sig),
            "latency_ms":   _lerp(95,    680,  sig),
            "cpu_util":     _lerp(0.35,  0.86, sig),
            "timeout_rate": _lerp(0.001, 0.07, sig),
        }, rng)

        db_t = max(0.0, (step - 12) / 16)
        db_sig = _sigmoid(db_t, center=0.45, steepness=5)
        frame["database"] = _build_step(HEALTHY_BASE["database"], {
            "latency_ms":  _lerp(18,   420,  db_sig),
            "error_rate":  _lerp(0.001, 0.04, db_sig),
            "cpu_util":    _lerp(0.28,  0.72, db_sig),
        }, rng)

        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "error_rate":   _lerp(0.003, 0.07, sig),
            "latency_ms":   _lerp(42,    380,  sig),
            "retry_rate":   _lerp(0.010, 0.14, sig),
        }, rng)

        frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
            "queue_depth": _lerp(8, 120, sig),
        }, rng)

        frame["auth"]     = _build_step(HEALTHY_BASE["auth"], {}, rng)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"],
            {"latency_ms": _lerp(38, 280, sig),
             "error_rate": _lerp(0.002, 0.04, sig)}, rng)
        frame["cache"] = _build_step(HEALTHY_BASE["cache"],
            {"cache_hit_rate": _lerp(0.96, 0.78, sig)}, rng)

        history.append(frame)
    return history


# ════════════════════════════════════════════════════════════════════════════
# CATEGORY 5: GEOPOLITICAL & REGULATORY
# ════════════════════════════════════════════════════════════════════════════

def scenario_regulatory_reroute(rng):
    """
    New data sovereignty law forces operator to reroute EU user traffic
    through a compliant region. Traffic takes longer paths.
    Timeline: sustained latency increase, cross-region database reads,
    no hard failure — but persistent SLO erosion.
    """
    history = []
    for step in range(TOTAL_STEPS):
        # Slow, sustained ramp — regulatory changes roll out gradually
        t = max(0.0, (step - 4) / 26)
        s = _sigmoid(t, 0.5, 4)  # gentler slope — regulatory not sudden

        frame = {}

        # Database reads now cross-region — latency increases significantly
        frame["database"] = _build_step(HEALTHY_BASE["database"], {
            "latency_ms":  _lerp(18,   280, s),
            "cpu_util":    _lerp(0.28, 0.62, s),
            "error_rate":  _lerp(0.001, 0.02, s),
        }, rng)

        # Auth needs to validate against remote data store
        frame["auth"] = _build_step(HEALTHY_BASE["auth"], {
            "latency_ms":  _lerp(28,   420, s),
            "timeout_rate": _lerp(0.000, 0.04, s),
        }, rng)

        # API gateway reflects longer backend round-trips
        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":  _lerp(42,   480, s),
            "retry_rate":  _lerp(0.010, 0.07, s),
        }, rng)

        # Frontend latency: users in affected region routed to new DC
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
            "latency_ms":  _lerp(38,   520, s),
        }, rng)

        # Workers need to read from non-local database
        frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
            "latency_ms":  _lerp(95,   560, s),
            "cpu_util":    _lerp(0.35, 0.61, s),
        }, rng)

        frame["cache"] = _build_step(HEALTHY_BASE["cache"], {
            "cache_hit_rate": _lerp(0.96, 0.74, s),  # cache locality lost
        }, rng)

        frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
            "queue_depth": _lerp(8, 90, s),
        }, rng)

        history.append(frame)
    return history


def scenario_cdn_sanctions(rng):
    """
    Primary CDN provider is sanctioned in key market — operator forced
    to failover to secondary CDN with 2× latency. Contract transition
    happens under operational pressure. Traffic routing is unstable
    during the switch.
    Timeline: latency spike during cutover → partial stabilization → residual degradation.
    """
    history = []
    for step in range(TOTAL_STEPS):
        # Cutover window: spike then partial stabilization
        t_cut = max(0.0, (step - 8) / 8)
        s_cut = _sigmoid(t_cut, 0.5, 9)

        t_stab = max(0.0, (step - 18) / 10)
        s_stab = _sigmoid(t_stab, 0.5, 6)

        # Residual degradation after cutover (worse CDN baseline)
        residual = 0.30

        effective_spike = s_cut * (1.0 - s_stab * 0.7)
        effective_base  = residual * s_stab

        frame = {}

        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
            "latency_ms":   _lerp(38,   2200, effective_spike) + _lerp(0, 180, effective_base),
            "error_rate":   _lerp(0.002, 0.18, effective_spike),
            "timeout_rate": _lerp(0.001, 0.12, effective_spike),
        }, rng)

        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":  _lerp(42,   1400, effective_spike) + _lerp(0, 120, effective_base),
            "error_rate":  _lerp(0.003, 0.09, effective_spike),
            "retry_rate":  _lerp(0.010, 0.24, effective_spike),
        }, rng)

        for svc in ("auth", "cache", "queue", "worker", "database"):
            frame[svc] = _build_step(HEALTHY_BASE[svc], {}, rng)

        history.append(frame)
    return history


# ════════════════════════════════════════════════════════════════════════════
# CATEGORY 6: ECONOMIC PRESSURE
# ════════════════════════════════════════════════════════════════════════════

def scenario_vendor_capacity_crunch(rng):
    """
    Cloud provider is capacity-constrained in this region due to AI compute demand.
    Auto-scaling requests return InstanceLimitExceeded.
    Traffic grows but compute cannot scale — resource exhaustion cascades.
    Timeline: resource pressure → worker saturation → queue build → customer impact.
    """
    history = []
    for step in range(TOTAL_STEPS):
        t = max(0.0, (step - 6) / 22)
        s = _sigmoid(t, 0.42, 6)

        frame = {}

        # Workers can't scale — existing workers run hotter and hotter
        frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
            "cpu_util":     _lerp(0.35, 0.99, s),
            "latency_ms":   _lerp(95,   920,  s),
            "error_rate":   _lerp(0.002, 0.09, s),
            "connection_count": _lerp(28, 400, s),
        }, rng)

        # Queue builds as workers are saturated
        frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
            "queue_depth": _lerp(8,   550, s),
            "cpu_util":    _lerp(0.12, 0.60, s),
        }, rng)

        # Database under connection pressure (workers retrying harder)
        db_t = max(0.0, (step - 10) / 18)
        db_s = _sigmoid(db_t, 0.40, 5)
        frame["database"] = _build_step(HEALTHY_BASE["database"], {
            "cpu_util":         _lerp(0.28, 0.86, db_s),
            "connection_count": _lerp(55,   480,  db_s),
            "latency_ms":       _lerp(18,   420,  db_s),
        }, rng)

        api_t = max(0.0, (step - 14) / 14)
        api_s = _sigmoid(api_t, 0.4, 5)
        frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
            "latency_ms":  _lerp(42,   680,  api_s),
            "error_rate":  _lerp(0.003, 0.06, api_s),
        }, rng)

        frame["cache"] = _build_step(HEALTHY_BASE["cache"], {
            "cache_hit_rate": _lerp(0.96, 0.65, s),
        }, rng)

        frame["auth"]     = _build_step(HEALTHY_BASE["auth"], {}, rng)
        frame["frontend"] = _build_step(HEALTHY_BASE["frontend"],
            {"latency_ms": _lerp(38, 620, api_s)}, rng)

        history.append(frame)
    return history


def scenario_cost_cut_redundancy(rng):
    """
    Operator eliminates redundant components to cut cloud spend.
    Single points of failure emerge. One component fails — no fallback.
    Timeline: healthy until single-component failure → immediate hard cascade.
    """
    history = []
    FAILURE_STEP = 14
    for step in range(TOTAL_STEPS):
        frame = {}

        if step < FAILURE_STEP:
            for svc, base in HEALTHY_BASE.items():
                frame[svc] = _build_step(base, {}, rng, noise_scale=0.025)
        else:
            # Cache is the single point that fails (redundant nodes were removed)
            t = min(1.0, (step - FAILURE_STEP) / 10)
            s = _sigmoid(t, 0.3, 9)

            frame["cache"] = _build_step(HEALTHY_BASE["cache"], {
                "cache_hit_rate": _lerp(0.96, 0.05, s),
                "error_rate":     _lerp(0.00, 0.55, s),
                "cpu_util":       _lerp(0.10, 0.99, s),
            }, rng)

            # All services that depend on cache get hit
            frame["api_gateway"] = _build_step(HEALTHY_BASE["api_gateway"], {
                "latency_ms":   _lerp(42,   1400, s),
                "error_rate":   _lerp(0.003, 0.28, s),
                "cpu_util":     _lerp(0.22,  0.91, s),
                "retry_rate":   _lerp(0.010, 0.31, s),
            }, rng)

            frame["worker"] = _build_step(HEALTHY_BASE["worker"], {
                "latency_ms":  _lerp(95,   1100, s),
                "error_rate":  _lerp(0.002, 0.18, s),
                "cpu_util":    _lerp(0.35,  0.93, s),
            }, rng)

            frame["database"] = _build_step(HEALTHY_BASE["database"], {
                "latency_ms":         _lerp(18,   680,  s),
                "connection_count":   _lerp(55,   490,  s),
                "cpu_util":           _lerp(0.28,  0.88, s),
            }, rng)

            t2 = max(0.0, (step - FAILURE_STEP - 3) / 10)
            s2 = _sigmoid(t2, 0.35, 7)
            frame["frontend"] = _build_step(HEALTHY_BASE["frontend"], {
                "error_rate": _lerp(0.002, 0.22, s2),
                "latency_ms": _lerp(38,   1600, s2),
            }, rng)

            frame["auth"]  = _build_step(HEALTHY_BASE["auth"], {
                "latency_ms": _lerp(28, 580, s * 0.8),
            }, rng)
            frame["queue"] = _build_step(HEALTHY_BASE["queue"], {
                "queue_depth": _lerp(8, 280, s),
            }, rng)

        history.append(frame)
    return history


# ════════════════════════════════════════════════════════════════════════════
# CONTEXT INTELLIGENCE — pre-signal world factors per scenario
# ════════════════════════════════════════════════════════════════════════════
# Each context layer represents a real-world causal domain that exists
# BEFORE telemetry signals start moving. This is PulseGrid's core thesis:
# cloud infrastructure failure originates in the physical world.

CONTEXT_INTELLIGENCE = {
    "healthy_baseline": {
        "summary": "All systems operating within normal parameters.",
        "layers": []
    },
    "hurricane_datacenter": {
        "summary": "Category 3 hurricane making landfall near primary cloud region.",
        "layers": [
            {"name": "Physical Infrastructure", "color": "#f59e0b", "signals": [
                "Hurricane Ida (Cat 3) — landfall projected 80mi from us-east-1 cluster",
                "3 of 5 datacenter cooling units under thermal stress",
                "Generator fuel reserves at 71% — resupply convoy delayed by road closures",
            ]},
            {"name": "Power & Energy", "color": "#ef4444", "signals": [
                "Regional grid frequency deviation: 59.6 Hz (nominal: 60.0 Hz)",
                "Utility company issued voltage reduction advisory — 6% brownout possible",
                "UPS failover testing suspended due to storm risk",
            ]},
            {"name": "Network & Connectivity", "color": "#3b82f6", "signals": [
                "BGP withdrawals on coastal fiber routes — storm damage risk",
                "Peering point at Miami-NAP showing elevated packet loss",
                "Satellite backup links pre-activated as redundancy measure",
            ]},
            {"name": "Operational", "color": "#8b5cf6", "signals": [
                "On-site staff evacuation order issued — remote operations only",
                "Incident bridge pre-opened with cloud provider support",
                "DR runbooks confirmed current — last tested 47 days ago",
            ]},
        ]
    },
    "power_grid_brownout": {
        "summary": "Regional power authority issued brownout notice — sustained voltage reduction.",
        "layers": [
            {"name": "Power & Energy", "color": "#ef4444", "signals": [
                "Power authority issued voltage reduction: 8% below nominal",
                "Peak summer demand exceeded grid capacity by 14% in affected region",
                "Predicted brownout duration: 4–8 hours until overnight demand drop",
            ]},
            {"name": "Physical Infrastructure", "color": "#f59e0b", "signals": [
                "Server thermal management entering passive cooling mode",
                "CPU frequency scaling engaged: all nodes throttled to 70% clock",
                "CRAC units consuming 30% more power to maintain temperature under load",
            ]},
            {"name": "Economic", "color": "#10b981", "signals": [
                "Spot pricing for backup generator diesel up 42% this quarter",
                "Long-term power contract expires in 3 months — no renewal confirmed",
                "Cloud region power cost now 2.3× operational budget allocation",
            ]},
        ]
    },
    "seismic_failure": {
        "summary": "6.2 magnitude earthquake strikes subregion hosting database and worker cluster.",
        "layers": [
            {"name": "Physical Infrastructure", "color": "#ef4444", "signals": [
                "USGS reported 6.2M earthquake — epicenter 12mi from Datacenter Zone B",
                "Automatic seismic shutdowns triggered in two server rows",
                "Physical fiber conduits under building at risk — structural assessment pending",
            ]},
            {"name": "Power & Energy", "color": "#f59e0b", "signals": [
                "Zone B on emergency generator power — main feed severed",
                "UPS battery at 100% but runtime limited to 45 minutes",
                "Grid restoration ETA from utility: 3–6 hours",
            ]},
            {"name": "Operational", "color": "#8b5cf6", "signals": [
                "Staff safety check in progress — operations running remotely",
                "DR failover procedure initiated — awaiting confirmation from Zone A",
                "Customer communication SLA: notify within 15 minutes of confirmed outage",
            ]},
            {"name": "Network & Connectivity", "color": "#3b82f6", "signals": [
                "Internal backbone links between Zone A and Zone B dropped",
                "External traffic automatically rerouting via Zone A — capacity at 140%",
            ]},
        ]
    },
    "retry_storm": {
        "summary": "Auth service failure triggering aggressive client retry behavior.",
        "layers": [
            {"name": "Software & Configuration", "color": "#3b82f6", "signals": [
                "Auth service v2.4.1 deployed 18 minutes ago — no circuit breaker configured",
                "Client retry policy: 5 attempts, 100ms fixed interval — no backoff",
                "Auth service pool size fixed at 12 instances — no autoscaling",
            ]},
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "Auth database connection pool at 94% utilization",
                "Thread exhaustion detected in API gateway auth middleware",
                "Load balancer health checks showing auth backend oscillating",
            ]},
            {"name": "Operational", "color": "#8b5cf6", "signals": [
                "On-call engineer notified — response pending",
                "Recent deployment: JWT token validation library upgraded",
                "No rollback procedure tested for this auth service version",
            ]},
        ]
    },
    "dns_degradation": {
        "summary": "Primary DNS resolver experiencing lookup failures and increased latency.",
        "layers": [
            {"name": "Network & Connectivity", "color": "#3b82f6", "signals": [
                "Primary DNS resolver (8.8.8.8) showing intermittent packet loss",
                "DNS query latency: 380ms average (normal: 8ms)",
                "Secondary resolver TTL not configured — no automatic fallback",
            ]},
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "Resolver infrastructure undergoing maintenance at upstream provider",
                "Local DNS cache TTL set to 300s — stale entries persisting",
                "Service discovery using DNS-based lookup — no sidecar mesh configured",
            ]},
            {"name": "Economic", "color": "#10b981", "signals": [
                "DNS provider contract being renegotiated — SLA currently suspended",
                "Budget constraint prevented migration to anycast resolver last quarter",
            ]},
        ]
    },
    "bgp_route_leak": {
        "summary": "Misconfigured BGP peer announced incorrect routes — traffic misdirected globally.",
        "layers": [
            {"name": "Network & Connectivity", "color": "#3b82f6", "signals": [
                "BGP route leak detected: 4,200+ prefixes announced by AS64512 incorrectly",
                "Traffic to us-east-1 being routed through 3 additional AS hops",
                "Peering relationships with 2 Tier-1 ISPs showing anomalous announcements",
            ]},
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "No RPKI (Route Origin Validation) configured on affected peer sessions",
                "BGP filters not enforced for max-prefix limits on this peering point",
                "NOC alerted — BGP filter update estimated 20–40 minutes to propagate",
            ]},
            {"name": "Geopolitical", "color": "#a855f7", "signals": [
                "Affected AS is operated by state-adjacent entity in restricted jurisdiction",
                "Similar route leak pattern observed during geopolitical tension events in 2022",
                "Threat intelligence feed flagged AS64512 for anomalous routing 6 hours ago",
            ]},
        ]
    },
    "queue_backlog": {
        "summary": "Message ingestion rate exceeding worker processing capacity.",
        "layers": [
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "Worker autoscaling limit reached: 20 instances (hard cap)",
                "Queue partition count fixed at 8 — cannot add partitions without downtime",
                "Dead-letter queue growing: 1,240 messages pending review",
            ]},
            {"name": "Economic", "color": "#10b981", "signals": [
                "Cloud spend optimization: worker instance count reduced 40% last month",
                "Autoscaling max cap lowered from 50 to 20 instances to control costs",
                "Burst capacity budget exhausted for this billing period",
            ]},
            {"name": "Operational", "color": "#8b5cf6", "signals": [
                "Traffic spike coincides with marketing campaign launch — no capacity plan filed",
                "SRE team flagged worker saturation risk 2 weeks ago — ticket still open",
                "Consumer throughput monitoring alert suppressed during maintenance window",
            ]},
        ]
    },
    "regional_divergence": {
        "summary": "Worker pool in secondary region degrading — cross-region traffic divergence detected.",
        "layers": [
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "us-west-2 worker cluster showing hardware disk failures: 3 nodes affected",
                "Cross-region replication lag: 4.2 seconds (threshold: 500ms)",
                "Load balancer health checks inconsistent across regions",
            ]},
            {"name": "Physical Infrastructure", "color": "#ef4444", "signals": [
                "Data center in secondary region reported cooling anomaly yesterday",
                "Hardware refresh in secondary region deferred for 6 months",
            ]},
            {"name": "Operational", "color": "#8b5cf6", "signals": [
                "No region-aware traffic routing policy configured",
                "Multi-region failover runbook last updated 14 months ago",
            ]},
        ]
    },
    "regulatory_reroute": {
        "summary": "EU data sovereignty law forcing traffic rerouting — sustained SLO erosion.",
        "layers": [
            {"name": "Geopolitical & Regulatory", "color": "#a855f7", "signals": [
                "EU Data Act Article 23 enforcement begins today — 90-day grace period expired",
                "DPA issued formal compliance notice: EU user data must not leave EU jurisdiction",
                "Legal team confirmed: non-compliance carries €20M or 4% global revenue fine",
            ]},
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "Traffic rerouting to EU-compliant region: additional 120ms round-trip latency",
                "Cross-region database reads now required for all EU user requests",
                "CDN edge nodes in non-compliant regions being gradually decommissioned",
            ]},
            {"name": "Economic", "color": "#10b981", "signals": [
                "EU-compliant region infrastructure cost: 2.8× primary region",
                "Compliance audit budget: $340K allocated for this quarter",
                "SLO renegotiation with enterprise customers required — 12 contracts affected",
            ]},
        ]
    },
    "cdn_sanctions": {
        "summary": "Primary CDN provider sanctioned — emergency failover to secondary CDN underway.",
        "layers": [
            {"name": "Geopolitical & Regulatory", "color": "#a855f7", "signals": [
                "OFAC sanctions designate primary CDN operator as SDN — effective immediately",
                "US Treasury guidance: 30-day wind-down period for existing contracts",
                "Legal team: no extension possible — cutover must complete within 72 hours",
            ]},
            {"name": "Economic", "color": "#10b981", "signals": [
                "Secondary CDN contract: 2.4× cost per TB vs primary",
                "Emergency procurement approved: $2.1M annual contract for secondary CDN",
                "Performance SLA in secondary CDN: 95th percentile only (vs 99th in primary)",
            ]},
            {"name": "Network & Connectivity", "color": "#3b82f6", "signals": [
                "Secondary CDN has 40% fewer PoPs in Asia-Pacific — latency increases expected",
                "DNS propagation for CDN cutover: estimated 2–6 hours globally",
                "Origin pull traffic spiking during cutover — origin servers under elevated load",
            ]},
        ]
    },
    "vendor_capacity_crunch": {
        "summary": "Cloud provider capacity-constrained in this region — autoscaling blocked.",
        "layers": [
            {"name": "Economic", "color": "#10b981", "signals": [
                "AI compute demand consumed 78% of available GPU+CPU capacity in us-east-1",
                "Cloud provider announced: no new instance launches for c6i.xlarge class for 72h",
                "Spot instance market: 4× normal price — on-demand queue: estimated 8-hour wait",
            ]},
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "Autoscaling group: InstanceLimitExceeded errors since 09:14 UTC",
                "Existing worker fleet at 99% utilization — no headroom for traffic spikes",
                "Reserved instance coverage: 60% — insufficient for current traffic level",
            ]},
            {"name": "Physical Infrastructure", "color": "#ef4444", "signals": [
                "Regional data center expansion delayed 6 months — silicon supply chain backlog",
                "Power infrastructure at this AZ rated for 80MW — current draw: 76MW",
                "Hardware delivery lead times: 16–22 weeks for new server nodes",
            ]},
            {"name": "Geopolitical", "color": "#a855f7", "signals": [
                "Export controls restricting advanced GPU chip availability to US providers",
                "CHIPS Act datacenter expansion subsidies delayed pending appropriations vote",
            ]},
        ]
    },
    "cost_cut_redundancy": {
        "summary": "Redundant infrastructure removed to cut cloud spend — single point of failure exposed.",
        "layers": [
            {"name": "Economic", "color": "#10b981", "signals": [
                "Q3 cost optimization: cloud spend reduced 35% by eliminating redundant nodes",
                "Cache cluster reduced from 6 nodes to 2 nodes — no replication",
                "Chaos engineering and DR testing budget cut: last test was 11 months ago",
            ]},
            {"name": "Operational", "color": "#8b5cf6", "signals": [
                "SRE team flagged single-node cache risk in June — no action taken",
                "Runbook for cache failure last updated before redundancy was removed",
                "On-call rotation reduced from 3 engineers to 1 due to headcount cuts",
            ]},
            {"name": "Infrastructure", "color": "#f59e0b", "signals": [
                "Cache node running on last-gen hardware — scheduled replacement deferred",
                "No circuit breaker configured between API gateway and cache",
                "Cache failure mode: hard error (no fallback to database implemented)",
            ]},
        ]
    },
}


# ════════════════════════════════════════════════════════════════════════════
# CATEGORIES & SCENARIO REGISTRY
# ════════════════════════════════════════════════════════════════════════════

CATEGORIES = {
    "baseline": {
        "label": "Baseline",
        "description": "Normal operating conditions",
        "scenarios": ["healthy_baseline"],
    },
    "natural_disaster": {
        "label": "Natural Disaster & Environmental",
        "description": "Physical world events threatening datacenter infrastructure",
        "scenarios": ["hurricane_datacenter", "power_grid_brownout", "seismic_failure"],
    },
    "infrastructure": {
        "label": "Infrastructure & Network",
        "description": "Hardware, routing, and connectivity failures",
        "scenarios": ["bgp_route_leak", "dns_degradation"],
    },
    "cascade_failure": {
        "label": "Cascade Failure Patterns",
        "description": "Software and service interdependency failures",
        "scenarios": ["retry_storm", "queue_backlog", "regional_divergence"],
    },
    "geopolitical": {
        "label": "Geopolitical & Regulatory",
        "description": "Policy, sanctions, and regulatory impacts on cloud infrastructure",
        "scenarios": ["regulatory_reroute", "cdn_sanctions"],
    },
    "economic": {
        "label": "Economic Pressure",
        "description": "Cost, vendor, and capacity constraint failures",
        "scenarios": ["vendor_capacity_crunch", "cost_cut_redundancy"],
    },
}

SCENARIO_META = {
    "healthy_baseline": {
        "label": "Healthy Baseline",
        "category": "baseline",
        "description": "All systems nominal. Minor telemetry noise only.",
        "fn": scenario_healthy,
        "onset_step": None,
    },
    "hurricane_datacenter": {
        "label": "Hurricane: Datacenter Region",
        "category": "natural_disaster",
        "description": "Category 3 hurricane making landfall near cloud region — thermal stress, network degradation.",
        "fn": scenario_hurricane_datacenter,
        "onset_step": 7,
    },
    "power_grid_brownout": {
        "label": "Power Grid Brownout",
        "category": "natural_disaster",
        "description": "Regional brownout — voltage reduction causes uniform CPU throttling across all services.",
        "fn": scenario_power_grid_brownout,
        "onset_step": 6,
    },
    "seismic_failure": {
        "label": "Seismic Zone Failure",
        "category": "natural_disaster",
        "description": "6.2M earthquake near datacenter — sudden step-change failure, no graceful shutdown.",
        "fn": scenario_seismic_failure,
        "onset_step": 10,
    },
    "bgp_route_leak": {
        "label": "BGP Route Leak",
        "category": "infrastructure",
        "description": "Misconfigured BGP peer misdirects global traffic — latency spike, timeout clustering, partial recovery.",
        "fn": scenario_bgp_route_leak,
        "onset_step": 5,
    },
    "dns_degradation": {
        "label": "DNS Resolver Degradation",
        "category": "infrastructure",
        "description": "DNS resolver degrades — timeout clustering appears before hard errors.",
        "fn": scenario_dns_degradation,
        "onset_step": 6,
    },
    "retry_storm": {
        "label": "Retry Storm",
        "category": "cascade_failure",
        "description": "Auth service fails — aggressive client retries amplify load, API gateway overloads.",
        "fn": scenario_retry_storm,
        "onset_step": 8,
    },
    "queue_backlog": {
        "label": "Queue Backlog",
        "category": "cascade_failure",
        "description": "Message ingestion exceeds worker capacity — queue depth grows, cascading load.",
        "fn": scenario_queue_backlog,
        "onset_step": 7,
    },
    "regional_divergence": {
        "label": "Regional Divergence",
        "category": "cascade_failure",
        "description": "One region's workers degrade — intermittent errors, replication lag.",
        "fn": scenario_regional_divergence,
        "onset_step": 8,
    },
    "regulatory_reroute": {
        "label": "Regulatory Forced Reroute",
        "category": "geopolitical",
        "description": "EU data sovereignty law forces traffic rerouting — sustained SLO erosion, no hard failure.",
        "fn": scenario_regulatory_reroute,
        "onset_step": 4,
    },
    "cdn_sanctions": {
        "label": "CDN Provider Sanctioned",
        "category": "geopolitical",
        "description": "Primary CDN operator sanctioned — emergency cutover to secondary CDN with 2× latency.",
        "fn": scenario_cdn_sanctions,
        "onset_step": 8,
    },
    "vendor_capacity_crunch": {
        "label": "Vendor Capacity Crunch",
        "category": "economic",
        "description": "Cloud provider capacity-constrained due to AI demand — autoscaling blocked, resource exhaustion.",
        "fn": scenario_vendor_capacity_crunch,
        "onset_step": 6,
    },
    "cost_cut_redundancy": {
        "label": "Cost-Cut Redundancy Loss",
        "category": "economic",
        "description": "Redundant cache nodes removed to cut spend — single point of failure causes hard cascade.",
        "fn": scenario_cost_cut_redundancy,
        "onset_step": 14,
    },
}


def get_scenario_history(name: str):
    if name not in SCENARIO_META:
        name = "healthy_baseline"
    meta = SCENARIO_META[name]
    rng  = random.Random(NOISE_SEED)
    return meta["fn"](rng)


def get_scenario_context(name: str) -> dict:
    return CONTEXT_INTELLIGENCE.get(name, {"summary": "", "layers": []})


def list_scenarios():
    return [
        {
            "id":          k,
            "label":       v["label"],
            "category":    v["category"],
            "description": v["description"],
            "onset_step":  v["onset_step"],
        }
        for k, v in SCENARIO_META.items()
    ]


def list_categories():
    return [
        {
            "id":          cat_id,
            "label":       cat["label"],
            "description": cat["description"],
            "scenarios":   cat["scenarios"],
        }
        for cat_id, cat in CATEGORIES.items()
    ]
