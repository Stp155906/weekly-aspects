from skyfield.api import load, Topos
from datetime import datetime, timedelta
from collections import Counter
import json

# =========================
# CONFIG
# =========================
ASPECT_TOLERANCE_DEG = 8.0   # fallback max orb (unused if ORBS has a value)
INCLUDE_SUN_MOON = True      # include luminaries to increase pattern hits
SIGN_NAMES = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
              "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]

# =========================
# SETUP SKYFIELD
# =========================
planets = load('de421.bsp')

planet_names = {
    'mercury': 'mercury',
    'venus': 'venus',
    'mars': 'mars',
    'jupiter': 'jupiter barycenter',
    'saturn': 'saturn barycenter',
    'uranus': 'uranus barycenter',
    'neptune': 'neptune barycenter'
}

if INCLUDE_SUN_MOON:
    planet_names.update({
        'sun': 'sun',
        'moon': 'moon'
    })

planetary_objects = {name: planets[planet_names[name]] for name in planet_names}

# Geocentric observer
earth = planets['earth']
observer = earth + Topos(latitude_degrees=0, longitude_degrees=0)

# =========================
# ASPECT DEFINITIONS / MAPPINGS
# =========================
ASPECT_DEFS = {
    "conjunction": 0.0,
    "semi-sextile": 30.0,
    "semi-square": 45.0,
    "sextile": 60.0,
    "quintile": 72.0,
    "square": 90.0,
    "trine": 120.0,
    "sesquiquadrate": 135.0,
    "quincunx": 150.0,
    "opposition": 180.0
}

ASPECT_FAMILY = {
    "conjunction": "1st-harmonic",
    "opposition": "2nd-harmonic",
    "trine": "3rd-harmonic",
    "square": "4th-harmonic",
    "sextile": "6th-harmonic",
    "quincunx": "12th-harmonic",
    "semi-sextile": "12th-harmonic",
    "semi-square": "8th-harmonic",
    "sesquiquadrate": "8th-harmonic",
    "quintile": "5th-harmonic"
}

ASPECT_VIBE = {
    "conjunction": "neutral",
    "opposition": "tension",
    "trine": "harmony",
    "square": "tension",
    "sextile": "harmony",
    "quincunx": "neutral",
    "semi-sextile": "neutral",
    "semi-square": "tension",
    "sesquiquadrate": "tension",
    "quintile": "harmony"
}

# Per-aspect orb limits (degrees)
ORBS = {
    "conjunction": 8,
    "opposition": 8,
    "trine": 6,
    "square": 6,
    "sextile": 4,
    "quincunx": 3,
    "quintile": 2,
    "semi-square": 2,
    "semi-sextile": 2,
    "sesquiquadrate": 2
}

# crude weights to nudge importance_score by body
BODY_WEIGHT = {
    "sun": 1.25, "moon": 1.25,
    "mercury": 1.0, "venus": 1.0, "mars": 1.05,
    "jupiter": 1.05, "saturn": 1.05,
    "uranus": 0.95, "neptune": 0.95,
}
def body_weight(name: str) -> float:
    return BODY_WEIGHT.get(name.lower(), 1.0)

# =========================
# MATH HELPERS
# =========================
def norm180(angle):
    """Normalize any angle to the 0..180 shortest separation."""
    a = angle % 360.0
    return a if a <= 180.0 else 360.0 - a

def angular_distance(a, b):
    """Shortest angular distance between two longitudes (deg)."""
    return norm180(abs(a - b))

# =========================
# CORE: CALCULATE PAIRWISE ASPECTS (WITH PHASE + ENRICHMENTS)
# =========================
def calculate_aspects(date):
    ts = load.timescale()
    t0 = ts.utc(date.year, date.month, date.day)
    t1 = ts.utc(date.year, date.month, date.day, 12)  # 0.5 days later for speed calc

    # positions + speeds (deg/day)
    positions = {}
    speeds = {}
    for name, planet in planetary_objects.items():
        lon0 = observer.at(t0).observe(planet).apparent().ecliptic_latlon()[1].degrees
        lon1 = observer.at(t1).observe(planet).apparent().ecliptic_latlon()[1].degrees
        delta = (lon1 - lon0 + 360.0) % 360.0
        if delta > 180.0:
            delta -= 360.0
        speed = delta / 0.5  # deg/day
        positions[name] = lon0 % 360.0
        speeds[name] = speed

    aspects = []

    names = sorted(positions.keys())
    for i in range(len(names)):
        p1 = names[i]
        for j in range(i+1, len(names)):
            p2 = names[j]
            lon1, lon2 = positions[p1], positions[p2]
            angle = angular_distance(lon1, lon2)

            # pick the single closest aspect for this pair
            best = None
            best_orb = 999.0
            for aspect_name, ideal in ASPECT_DEFS.items():
                orb_limit = ORBS.get(aspect_name, ASPECT_TOLERANCE_DEG)
                orb = abs(angle - ideal)
                if orb <= orb_limit and orb < best_orb:
                    best = (aspect_name, ideal, orb)
                    best_orb = orb

            if best:
                aspect_name, ideal, orb = best

                # determine phase (applying/separating) by projecting faster body
                faster, slower = (p1, p2) if abs(speeds[p1]) > abs(speeds[p2]) else (p2, p1)
                projected = (positions[faster] + speeds[faster]) % 360.0
                future_angle = angular_distance(projected, positions[slower])
                phase = "applying" if abs(future_angle - ideal) < orb else "separating"

                family = ASPECT_FAMILY.get(aspect_name, None)
                vibe = ASPECT_VIBE.get(aspect_name, "neutral")

                # sign / out_of_sign
                sign_idx1 = int(lon1 // 30)
                sign_idx2 = int(lon2 // 30)
                sign1 = SIGN_NAMES[sign_idx1]
                sign2 = SIGN_NAMES[sign_idx2]

                diff_signs = abs(sign_idx1 - sign_idx2) % 12
                expected = None
                if diff_signs == 0:
                    expected = "conjunction"
                elif diff_signs in (2, 10):
                    expected = "sextile"
                elif diff_signs in (3, 9):
                    expected = "square"
                elif diff_signs in (4, 8):
                    expected = "trine"
                elif diff_signs == 6:
                    expected = "opposition"
                out_of_sign = (expected != aspect_name)

                # importance score (tightness * avg body weight)
                tightness = max(0.0, 1.0 - (orb / ORBS.get(aspect_name, ASPECT_TOLERANCE_DEG)))
                w = (body_weight(p1) + body_weight(p2)) / 2.0
                importance_score = round(min(1.0, tightness * w), 3)

                aspects.append({
                    "body1": p1,
                    "body2": p2,
                    "aspect_name": aspect_name,
                    "family": family,
                    "vibe": vibe,
                    "ideal_angle_deg": ideal,
                    "angle_measured_deg": round(angle, 3),
                    "orb_deg": round(orb, 3),
                    "phase": phase,
                    "out_of_sign": out_of_sign,
                    "positions": {
                        p1: {"lon_deg": round(lon1, 2), "sign": sign1, "speed_deg_per_day": round(speeds[p1], 3)},
                        p2: {"lon_deg": round(lon2, 2), "sign": sign2, "speed_deg_per_day": round(speeds[p2], 3)}
                    },
                    "importance_score": importance_score
                })

    return aspects

# =========================
# PATTERN DETECTION HELPERS
# =========================
def has_aspect(aspects, a, b, aspect_name):
    """True if aspects contains the named aspect between bodies a & b (orderless)."""
    s = {a, b}
    for asp in aspects:
        if {asp["body1"], asp["body2"]} == s and asp["aspect_name"] == aspect_name:
            return True
    return False

def edge(aspect_name, a, b):
    """Edge dict with bodies sorted for consistency."""
    x, y = sorted([a, b])
    return {"body1": x, "body2": y, "aspect_name": aspect_name}

def unique_fingerprint(members, pattern_type):
    return (pattern_type, tuple(sorted(members)))

def bodies_from(aspects):
    return sorted(list({asp["body1"] for asp in aspects} | {asp["body2"] for asp in aspects}))

# =========================
# INDIVIDUAL PATTERN DETECTORS
# =========================
def detect_yods(aspects):
    patterns, seen = [], set()
    b = bodies_from(aspects)
    n = len(b)
    for i in range(n):
        for j in range(i+1, n):
            for k in range(j+1, n):
                a1, a2, apex = b[i], b[j], b[k]
                triplets = [(a1, a2, apex), (a1, apex, a2), (a2, apex, a1)]
                for A, B, C in triplets:
                    if (has_aspect(aspects, A, B, "sextile") and
                        has_aspect(aspects, A, C, "quincunx") and
                        has_aspect(aspects, B, C, "quincunx")):
                        fp = unique_fingerprint([A, B, C], "Yod")
                        if fp in seen: 
                            continue
                        seen.add(fp)
                        patterns.append({
                            "pattern_type": "Yod",
                            "members": sorted([A, B, C]),
                            "edges": [
                                edge("sextile", A, B),
                                edge("quincunx", A, C),
                                edge("quincunx", B, C)
                            ],
                            "pattern_score": 0.8
                        })
    return patterns

def detect_tsquares(aspects):
    patterns, seen = [], set()
    b = bodies_from(aspects)
    n = len(b)
    for i in range(n):
        for j in range(i+1, n):
            for k in range(j+1, n):
                A, B, C = b[i], b[j], b[k]
                perms = [(A,B,C), (A,C,B), (B,C,A)]
                for X, Y, Z in perms:
                    if (has_aspect(aspects, X, Y, "opposition") and
                        has_aspect(aspects, X, Z, "square") and
                        has_aspect(aspects, Y, Z, "square")):
                        fp = unique_fingerprint([X, Y, Z], "T-Square")
                        if fp in seen: 
                            continue
                        seen.add(fp)
                        patterns.append({
                            "pattern_type": "T-Square",
                            "members": sorted([X, Y, Z]),
                            "edges": [
                                edge("opposition", X, Y),
                                edge("square", X, Z),
                                edge("square", Y, Z)
                            ],
                            "pattern_score": 0.85
                        })
    return patterns

def detect_grand_trines(aspects):
    patterns, seen = [], set()
    b = bodies_from(aspects)
    n = len(b)
    for i in range(n):
        for j in range(i+1, n):
            for k in range(j+1, n):
                A, B, C = b[i], b[j], b[k]
                if (has_aspect(aspects, A, B, "trine") and
                    has_aspect(aspects, A, C, "trine") and
                    has_aspect(aspects, B, C, "trine")):
                    fp = unique_fingerprint([A, B, C], "Grand Trine")
                    if fp in seen:
                        continue
                    seen.add(fp)
                    patterns.append({
                        "pattern_type": "Grand Trine",
                        "members": sorted([A, B, C]),
                        "edges": [
                            edge("trine", A, B),
                            edge("trine", A, C),
                            edge("trine", B, C)
                        ],
                        "pattern_score": 0.8
                    })
    return patterns

def detect_kites(aspects):
    patterns, seen = [], set()
    b = bodies_from(aspects)
    n = len(b)
    for i in range(n):
        for j in range(i+1, n):
            for k in range(j+1, n):
                A, B, C = b[i], b[j], b[k]
                if (has_aspect(aspects, A, B, "trine") and
                    has_aspect(aspects, A, C, "trine") and
                    has_aspect(aspects, B, C, "trine")):
                    for d in b:
                        if d in (A, B, C):
                            continue
                        if (has_aspect(aspects, d, A, "opposition") and
                            has_aspect(aspects, d, B, "sextile") and
                            has_aspect(aspects, d, C, "sextile")):
                            members = sorted([A, B, C, d])
                            fp = unique_fingerprint(members, "Kite")
                            if fp in seen: 
                                continue
                            seen.add(fp)
                            patterns.append({
                                "pattern_type": "Kite",
                                "members": members,
                                "edges": [
                                    edge("trine", A, B), edge("trine", A, C), edge("trine", B, C),
                                    edge("opposition", d, A),
                                    edge("sextile", d, B), edge("sextile", d, C)
                                ],
                                "pattern_score": 0.86
                            })
                        if (has_aspect(aspects, d, B, "opposition") and
                            has_aspect(aspects, d, A, "sextile") and
                            has_aspect(aspects, d, C, "sextile")):
                            members = sorted([A, B, C, d])
                            fp = unique_fingerprint(members, "Kite")
                            if fp in seen: 
                                continue
                            seen.add(fp)
                            patterns.append({
                                "pattern_type": "Kite",
                                "members": members,
                                "edges": [
                                    edge("trine", A, B), edge("trine", A, C), edge("trine", B, C),
                                    edge("opposition", d, B),
                                    edge("sextile", d, A), edge("sextile", d, C)
                                ],
                                "pattern_score": 0.86
                            })
                        if (has_aspect(aspects, d, C, "opposition") and
                            has_aspect(aspects, d, A, "sextile") and
                            has_aspect(aspects, d, B, "sextile")):
                            members = sorted([A, B, C, d])
                            fp = unique_fingerprint(members, "Kite")
                            if fp in seen: 
                                continue
                            seen.add(fp)
                            patterns.append({
                                "pattern_type": "Kite",
                                "members": members,
                                "edges": [
                                    edge("trine", A, B), edge("trine", A, C), edge("trine", B, C),
                                    edge("opposition", d, C),
                                    edge("sextile", d, A), edge("sextile", d, B)
                                ],
                                "pattern_score": 0.86
                            })
    return patterns

def detect_mystic_rectangles(aspects):
    patterns, seen = [], set()
    b = bodies_from(aspects)
    n = len(b)
    for i in range(n):
        for j in range(i+1, n):
            for k in range(j+1, n):
                for m in range(k+1, n):
                    A, B, C, D = b[i], b[j], b[k], b[m]
                    if (has_aspect(aspects, A, B, "opposition") and
                        has_aspect(aspects, C, D, "opposition")):
                        if (has_aspect(aspects, A, C, "sextile") and
                            has_aspect(aspects, A, D, "sextile") and
                            has_aspect(aspects, B, C, "sextile") and
                            has_aspect(aspects, B, D, "sextile")):
                            members = sorted([A, B, C, D])
                            fp = unique_fingerprint(members, "Mystic Rectangle")
                            if fp in seen: 
                                continue
                            seen.add(fp)
                            patterns.append({
                                "pattern_type": "Mystic Rectangle",
                                "members": members,
                                "edges": [
                                    edge("opposition", A, B), edge("opposition", C, D),
                                    edge("sextile", A, C), edge("sextile", A, D),
                                    edge("sextile", B, C), edge("sextile", B, D)
                                ],
                                "pattern_score": 0.84
                            })
    return patterns

def detect_grand_crosses(aspects):
    patterns, seen = [], set()
    b = bodies_from(aspects)
    n = len(b)
    for i in range(n):
        for j in range(i+1, n):
            for k in range(j+1, n):
                for m in range(k+1, n):
                    A, B, C, D = b[i], b[j], b[k], b[m]
                    # try a few pairings for the two oppositions
                    oppositions = [(A, C, B, D), (A, B, C, D), (A, D, B, C), (B, C, A, D)]
                    for X, Y, U, V in oppositions:
                        if (has_aspect(aspects, X, Y, "opposition") and
                            has_aspect(aspects, U, V, "opposition")):
                            sq_ok = (
                                has_aspect(aspects, X, U, "square") and
                                has_aspect(aspects, U, Y, "square") and
                                has_aspect(aspects, Y, V, "square") and
                                has_aspect(aspects, V, X, "square")
                            )
                            if sq_ok:
                                members = sorted([A, B, C, D])
                                fp = unique_fingerprint(members, "Grand Cross")
                                if fp in seen: 
                                    continue
                                seen.add(fp)
                                patterns.append({
                                    "pattern_type": "Grand Cross",
                                    "members": members,
                                    "edges": [
                                        edge("opposition", X, Y), edge("opposition", U, V),
                                        edge("square", X, U), edge("square", U, Y),
                                        edge("square", Y, V), edge("square", V, X)
                                    ],
                                    "pattern_score": 0.88
                                })
    return patterns

# =========================
# PATTERN POST-PROCESS
# =========================
def flag_out_of_sign(patterns, aspects):
    """Add `has_out_of_sign` to each pattern if any of its edges are out-of-sign."""
    edge_lookup = {}
    for asp in aspects:
        key = frozenset([asp["body1"], asp["body2"], asp["aspect_name"]])
        edge_lookup[key] = asp.get("out_of_sign", False)

    for pat in patterns:
        has_ooo = False
        for e in pat["edges"]:
            key = frozenset([e["body1"], e["body2"], e["aspect_name"]])
            if edge_lookup.get(key, False):
                has_ooo = True
                break
        pat["has_out_of_sign"] = has_ooo
    return patterns

# =========================
# WEEKLY PIPELINE
# =========================
def debug_aspect_counts(aspects):
    c = Counter(a["aspect_name"] for a in aspects)
    return dict(c)

def _edge_lookup_by_pair(aspects):
    """Map (bodyA, bodyB, aspect_name) -> aspect dict for quick lookup."""
    L = {}
    for asp in aspects:
        key = (tuple(sorted([asp["body1"], asp["body2"]])), asp["aspect_name"])
        L[key] = asp
    return L

def _has_luminary(members):
    m = {x.lower() for x in members}
    return ("sun" in m) or ("moon" in m)

def add_pattern_strength_scores(patterns, aspects):
    """
    Compute pattern_strength_score in [0,1] for each pattern:
      - base = average edge tightness (1 - orb/orb_limit)
      - -0.10 penalty if has_out_of_sign
      - +0.05 bonus if Sun or Moon in members
    """
    lookup = _edge_lookup_by_pair(aspects)

    def tightness_for_edge(e):
        key = (tuple(sorted([e["body1"], e["body2"]])), e["aspect_name"])
        asp = lookup.get(key)
        if not asp:
            return 0.0
        aspect_name = asp["aspect_name"]
        orb = float(asp.get("orb_deg", 999.0))
        limit = float(ORBS.get(aspect_name, ASPECT_TOLERANCE_DEG))
        t = max(0.0, 1.0 - orb/limit)  # 0..1
        return t

    for pat in patterns:
        if not pat.get("edges"):
            pat["pattern_strength_score"] = 0.0
            continue

        # average edge tightness
        ts = [tightness_for_edge(e) for e in pat["edges"]]
        base = sum(ts) / len(ts)

        # penalties/bonuses
        score = base
        if pat.get("has_out_of_sign"):
            score -= 0.10
        if _has_luminary(pat.get("members", [])):
            score += 0.05

        # clamp
        score = max(0.0, min(1.0, score))
        pat["pattern_strength_score"] = round(score, 3)

    return patterns


def fetch_weekly_aspects(start_date, days=7):
    weekly_aspects = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        aspects = calculate_aspects(date)

        # Detect patterns
        patterns = []
        patterns.extend(detect_yods(aspects))
        patterns.extend(detect_tsquares(aspects))
        patterns.extend(detect_grand_trines(aspects))
        patterns.extend(detect_kites(aspects))
        patterns.extend(detect_mystic_rectangles(aspects))
        patterns.extend(detect_grand_crosses(aspects))

        # Flag out-of-sign at the pattern level
        patterns = flag_out_of_sign(patterns, aspects)
        patterns = add_pattern_strength_scores(patterns, aspects)  # <— add this line

        # Optional: quick sanity log
        counts = debug_aspect_counts(aspects)
        print(date.strftime('%Y-%m-%d'), "Aspect counts:", counts, "| Patterns:", [p["pattern_type"] for p in patterns])

        weekly_aspects.append({
            "date": date.strftime('%Y-%m-%d'),
            "aspects": aspects,
            "patterns": patterns
        })
    return weekly_aspects

# =========================
# RUN
# =========================
if __name__ == "__main__":
    start_date = datetime.utcnow()
    weekly_aspects = fetch_weekly_aspects(start_date, days=7)

    def save_to_json(data, filename="weekly_aspects.json"):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)

    payload = {"weekly_aspects": weekly_aspects}
    save_to_json(payload)
    print(json.dumps(payload, indent=2))
