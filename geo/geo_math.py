"""
Pure, dependency-free geospatial and ETA arithmetic.

Everything in this module is deterministic and database-free so that it can be
unit-tested in isolation and reused by the evaluation scripts. The database-
backed route snapping lives in ``app.algorithms``.
"""
import math
from typing import List, Sequence, Tuple

EARTH_RADIUS_METERS = 6371000.0

# ETA blending parameters (see estimate_eta_minutes).
SCHEDULED_SPEED_KMH = 25.0
BLEND_FULL_TRUST_SPEED_KMH = 10.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def calculate_polyline_distance(coords: Sequence[Sequence[float]]) -> float:
    """Total length in metres of a polyline given as ``[[lon, lat], ...]``."""
    total = 0.0
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1][0], coords[i - 1][1]
        lon2, lat2 = coords[i][0], coords[i][1]
        total += haversine_distance(lat1, lon1, lat2, lon2)
    return total


def calculate_split_distances(
    coords: Sequence[Sequence[float]], progress: float
) -> Tuple[float, float, float]:
    """
    Returns ``(total, travelled, remaining)`` in metres for a polyline split at
    ``progress`` (a fraction in [0, 1]; values outside are clamped).
    """
    if not coords:
        return 0.0, 0.0, 0.0
    progress = min(1.0, max(0.0, float(progress)))
    total = calculate_polyline_distance(coords)
    travelled = total * progress
    remaining = total * (1.0 - progress)
    return total, travelled, remaining


def blended_speed_kmh(
    current_speed_kmh: float,
    scheduled_speed_kmh: float = SCHEDULED_SPEED_KMH,
    full_trust_speed_kmh: float = BLEND_FULL_TRUST_SPEED_KMH,
) -> float:
    """
    Blends the observed speed with a scheduled fallback speed.

    At or above ``full_trust_speed_kmh`` the observed speed is used as-is. Below
    it (a bus idling at a stop, GPS noise near zero) the estimate leans
    progressively toward the scheduled speed so the ETA does not explode toward
    infinity when a bus is momentarily stationary.
    """
    current = max(0.0, float(current_speed_kmh))
    if full_trust_speed_kmh <= 0:
        return current
    alpha = min(1.0, current / full_trust_speed_kmh)
    return (alpha * current) + ((1.0 - alpha) * scheduled_speed_kmh)


def estimate_eta_minutes(distance_remaining_m: float, current_speed_kmh: float) -> float:
    """
    ETA in minutes for ``distance_remaining_m`` at the blended speed.
    This is the estimator used by the live API; the baseline it is evaluated
    against is :func:`baseline_eta_minutes`.
    """
    distance = max(0.0, float(distance_remaining_m))
    speed_m_per_min = (blended_speed_kmh(current_speed_kmh) * 1000.0) / 60.0
    if speed_m_per_min <= 0:
        return float("inf")
    return round(distance / speed_m_per_min, 1)


def baseline_eta_minutes(
    distance_remaining_m: float, average_speed_kmh: float = SCHEDULED_SPEED_KMH
) -> float:
    """
    Naive baseline: remaining distance over a fixed average speed. The project
    proposal commits to reporting the live estimator's error relative to this.
    """
    if average_speed_kmh <= 0:
        return float("inf")
    speed_m_per_min = (average_speed_kmh * 1000.0) / 60.0
    return round(max(0.0, float(distance_remaining_m)) / speed_m_per_min, 1)


def absolute_errors(predicted: Sequence[float], observed: Sequence[float]) -> List[float]:
    """Element-wise absolute error; inputs must be the same length."""
    if len(predicted) != len(observed):
        raise ValueError("predicted and observed must have the same length")
    return [abs(float(p) - float(o)) for p, o in zip(predicted, observed)]


def percentile(values: Sequence[float], q: float) -> float:
    """
    Nearest-rank percentile (``q`` in [0, 100]) without numpy, so the evaluation
    scripts have no extra dependencies. Returns ``nan`` for an empty input.
    """
    if not values:
        return float("nan")
    if not 0 <= q <= 100:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(float(v) for v in values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[rank - 1]
