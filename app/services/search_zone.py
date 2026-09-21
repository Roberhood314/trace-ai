def zone_score(confidence: float | None, age_hours: float, distance_km: float) -> float:
    """
    Heuristic MVP only.
    Produces a 0..100 score to help order search zones.
    It is not an operational or legal decision.
    """
    c = max(0.0, min(1.0, confidence if confidence is not None else 0.5))
    time_factor = max(0.15, 1.0 - min(age_hours, 48.0) / 60.0)
    distance_factor = max(0.15, 1.0 - min(distance_km, 50.0) / 60.0)
    return round(100.0 * c * time_factor * distance_factor, 2)
