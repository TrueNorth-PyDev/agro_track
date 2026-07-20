"""
public_api/geo.py

Geocoding (Nominatim / OpenStreetMap) and road-distance (OSRM) helpers.

No external libraries required — uses only Python's stdlib urllib.
No API keys required — both services are free and open.

Rate limits:
  - Nominatim: max 1 request per second (enforced by their ToS).
    We call it once per address, twice per estimate request.
    No caching is implemented here; add Redis caching in production.
  - OSRM public demo server: no hard limit but should not be abused.
    Consider self-hosting for high-volume production use.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOMINATIM_URL   = "https://nominatim.openstreetmap.org/search"
OSRM_URL        = "http://router.project-osrm.org/route/v1/driving"

# Bias geocoding toward Nigeria so plain city names resolve correctly.
COUNTRY_BIAS    = "Nigeria"

# Real Nigerian roads are ~30 % longer than straight-line (crow-fly) distance.
# Used only as a last-resort fallback when OSRM is unreachable.
ROAD_FACTOR     = 1.30

# Minimum billable distance (km). Prevents ₦0 estimates for same-street trips.
MIN_DISTANCE_KM = 5.0

# Request timeout in seconds for both services.
REQUEST_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_json(url: str, description: str) -> Optional[dict]:
    """
    Perform a GET request and parse the JSON response.
    Returns None on any network or parsing error so callers can handle gracefully.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                # Nominatim requires a descriptive User-Agent per their ToS.
                "User-Agent": "AgroTrack/1.0 (ephraim.e@truenorthglobalsolutions.com)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        logger.warning("HTTP %s from %s (%s)", exc.code, description, url)
    except urllib.error.URLError as exc:
        logger.warning("Network error reaching %s: %s", description, exc.reason)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Failed to parse JSON from %s: %s", description, exc)
    except Exception as exc:
        logger.error("Unexpected error fetching %s: %s", description, exc)
    return None


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def geocode(address: str) -> Optional[Tuple[float, float]]:
    """
    Convert a plain-text address string to (latitude, longitude).

    Automatically appends ', Nigeria' if the address does not already
    reference a Nigerian state or country to bias results correctly.

    Returns:
        (lat, lon) tuple of floats, or None if geocoding fails.
    """
    # Bias toward Nigeria without duplicating the word if it's already there.
    query = address.strip()
    if COUNTRY_BIAS.lower() not in query.lower():
        query = f"{query}, {COUNTRY_BIAS}"

    params = urllib.parse.urlencode({
        "q":              query,
        "format":         "json",
        "limit":          1,
        "addressdetails": 0,
    })
    url  = f"{NOMINATIM_URL}?{params}"
    data = _fetch_json(url, f"Nominatim geocode: {query!r}")

    if not data:
        logger.warning("Nominatim returned no data for address: %r", query)
        return None

    if not isinstance(data, list) or len(data) == 0:
        logger.warning("Nominatim found no results for: %r", query)
        return None

    try:
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        logger.debug("Geocoded %r → (%.6f, %.6f)", query, lat, lon)
        return lat, lon
    except (KeyError, ValueError, TypeError) as exc:
        logger.warning("Unexpected Nominatim response shape: %s", exc)
        return None


def road_distance_km(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
) -> Optional[float]:
    """
    Calculate the actual road driving distance between two (lat, lon) pairs
    using the OSRM public routing engine.

    Returns:
        Distance in kilometres (float), or None if OSRM is unreachable.
    """
    # OSRM expects coordinates as  longitude,latitude  (GeoJSON order).
    orig_str = f"{origin[1]},{origin[0]}"
    dest_str = f"{destination[1]},{destination[0]}"
    url = (
        f"{OSRM_URL}/{orig_str};{dest_str}"
        "?overview=false&alternatives=false&steps=false"
    )

    data = _fetch_json(url, "OSRM route")

    if not data:
        return None

    try:
        code = data.get("code", "")
        if code != "Ok":
            logger.warning("OSRM returned non-Ok code: %s", code)
            return None

        # OSRM returns distance in metres.
        distance_m = data["routes"][0]["distance"]
        distance_km = distance_m / 1000.0
        logger.debug("OSRM road distance: %.2f km", distance_km)
        return distance_km
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logger.warning("Unexpected OSRM response shape: %s", exc)
        return None


def haversine_km(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
) -> float:
    """
    Calculate straight-line (crow-fly) distance between two (lat, lon) points
    using the Haversine formula, then apply the Nigerian road correction factor.

    Used as a fallback when OSRM is unreachable.

    Returns:
        Estimated road distance in kilometres (float).
    """
    import math

    lat1, lon1 = map(math.radians, origin)
    lat2, lon2 = map(math.radians, destination)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    earth_radius_km = 6_371.0
    straight_line   = earth_radius_km * c
    road_estimate   = straight_line * ROAD_FACTOR

    logger.debug(
        "Haversine straight-line: %.2f km → road estimate: %.2f km",
        straight_line,
        road_estimate,
    )
    return road_estimate


def resolve_distance(pickup_address: str, delivery_address: str) -> Tuple[float, str]:
    """
    Top-level helper: geocode both addresses, get road distance via OSRM,
    fall back to Haversine if OSRM fails.

    Returns:
        (distance_km, method) where method is one of:
            'osrm'      — actual road routing (most accurate)
            'haversine' — straight-line × road factor (fallback)

    Raises:
        ValueError — if either address cannot be geocoded at all.
    """
    # --- Geocode pickup ---
    origin_coords = geocode(pickup_address)
    if origin_coords is None:
        raise ValueError(
            f"Could not locate pickup address: '{pickup_address}'. "
            "Please provide a more specific address (e.g. include city/state)."
        )

    # --- Geocode delivery ---
    destination_coords = geocode(delivery_address)
    if destination_coords is None:
        raise ValueError(
            f"Could not locate delivery address: '{delivery_address}'. "
            "Please provide a more specific address (e.g. include city/state)."
        )

    # --- Attempt OSRM road routing ---
    distance_km = road_distance_km(origin_coords, destination_coords)
    if distance_km is not None:
        distance_km = max(distance_km, MIN_DISTANCE_KM)
        return round(distance_km, 2), "osrm"

    # --- OSRM unavailable — fall back to Haversine ---
    logger.warning(
        "OSRM unavailable; falling back to Haversine for '%s' → '%s'",
        pickup_address,
        delivery_address,
    )
    distance_km = haversine_km(origin_coords, destination_coords)
    distance_km = max(distance_km, MIN_DISTANCE_KM)
    return round(distance_km, 2), "haversine"
