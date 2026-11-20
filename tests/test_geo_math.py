"""
Unit tests for the pure geospatial / ETA arithmetic in app.geo_math.
These need no database and no third-party packages.
"""
import math

import pytest

from geo import geo_math as gm

# Two points in Lahore roughly 2.5 km apart (Minar-e-Pakistan -> Lahore Fort area).
LAT1, LON1 = 31.5925, 74.3095
LAT2, LON2 = 31.5880, 74.3150


def test_haversine_zero_for_identical_points():
    assert gm.haversine_distance(LAT1, LON1, LAT1, LON1) == 0.0


def test_haversine_symmetric_and_plausible():
    d1 = gm.haversine_distance(LAT1, LON1, LAT2, LON2)
    d2 = gm.haversine_distance(LAT2, LON2, LAT1, LON1)
    assert math.isclose(d1, d2)
    assert 600 < d1 < 900  # ~720 m


def test_haversine_known_distance_equator_degree():
    # One degree of longitude along the equator is ~111.19 km.
    d = gm.haversine_distance(0.0, 0.0, 0.0, 1.0)
    assert math.isclose(d, 111_194.9, rel_tol=1e-3)


def test_polyline_distance_sums_segments():
    coords = [[LON1, LAT1], [LON2, LAT2], [LON1, LAT1]]
    seg = gm.haversine_distance(LAT1, LON1, LAT2, LON2)
    assert math.isclose(gm.calculate_polyline_distance(coords), 2 * seg)


def test_polyline_distance_degenerate_inputs():
    assert gm.calculate_polyline_distance([]) == 0.0
    assert gm.calculate_polyline_distance([[LON1, LAT1]]) == 0.0


@pytest.mark.parametrize("progress", [0.0, 0.25, 0.5, 1.0])
def test_split_distances_partition_total(progress):
    coords = [[LON1, LAT1], [LON2, LAT2]]
    total, travelled, remaining = gm.calculate_split_distances(coords, progress)
    assert math.isclose(travelled + remaining, total)
    assert math.isclose(travelled, total * progress)


def test_split_distances_clamps_progress_outside_unit_interval():
    coords = [[LON1, LAT1], [LON2, LAT2]]
    _, travelled_hi, remaining_hi = gm.calculate_split_distances(coords, 1.7)
    _, travelled_lo, remaining_lo = gm.calculate_split_distances(coords, -0.3)
    assert remaining_hi == 0.0 and travelled_lo == 0.0
    assert travelled_hi > 0 and remaining_lo > 0


def test_split_distances_empty():
    assert gm.calculate_split_distances([], 0.5) == (0.0, 0.0, 0.0)


def test_blended_speed_uses_schedule_when_stationary():
    assert gm.blended_speed_kmh(0.0) == gm.SCHEDULED_SPEED_KMH


def test_blended_speed_trusts_observed_speed_at_or_above_threshold():
    assert gm.blended_speed_kmh(10.0) == 10.0
    assert gm.blended_speed_kmh(42.0) == 42.0


def test_blended_speed_is_monotonic_between_zero_and_threshold():
    speeds = [gm.blended_speed_kmh(v) for v in (0, 2, 4, 6, 8, 10)]
    # Starts at the scheduled speed (25) and decreases toward the observed speed (10).
    assert speeds[0] == gm.SCHEDULED_SPEED_KMH
    assert all(a >= b for a, b in zip(speeds, speeds[1:]))


def test_blended_speed_never_negative():
    assert gm.blended_speed_kmh(-15.0) == gm.SCHEDULED_SPEED_KMH


def test_eta_zero_distance_is_zero_minutes():
    assert gm.estimate_eta_minutes(0.0, 30.0) == 0.0


def test_eta_matches_hand_calculation_at_full_trust_speed():
    # 10 km at 30 km/h = 20 minutes.
    assert gm.estimate_eta_minutes(10_000.0, 30.0) == 20.0


def test_eta_stationary_bus_does_not_diverge():
    # With a stationary bus the schedule speed (25 km/h) is used: 5 km -> 12 min.
    eta = gm.estimate_eta_minutes(5_000.0, 0.0)
    assert math.isfinite(eta)
    assert eta == 12.0


def test_baseline_eta_is_distance_over_fixed_speed():
    assert gm.baseline_eta_minutes(5_000.0) == 12.0
    assert gm.baseline_eta_minutes(5_000.0, average_speed_kmh=50.0) == 6.0


def test_absolute_errors_and_percentile():
    pred = [10.0, 12.0, 8.0, 30.0]
    obs = [11.0, 10.0, 8.0, 20.0]
    errs = gm.absolute_errors(pred, obs)
    assert errs == [1.0, 2.0, 0.0, 10.0]
    assert gm.percentile(errs, 50) == 1.0
    assert gm.percentile(errs, 90) == 10.0
    assert math.isnan(gm.percentile([], 50))


def test_absolute_errors_length_mismatch_raises():
    with pytest.raises(ValueError):
        gm.absolute_errors([1.0], [1.0, 2.0])
