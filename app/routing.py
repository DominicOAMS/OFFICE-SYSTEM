import os

import requests
from dotenv import load_dotenv

load_dotenv()

ORS_API_KEY = os.environ.get("ORS_API_KEY")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"


def get_route_distance_km(waypoints):
    """Total one-way driving distance in km via OpenRouteService across an ordered list of
    (lat, lng) waypoints - the start point followed by one or more stops in visit order.
    Returns None if it can't be calculated (no API key configured, fewer than 2 waypoints,
    network error, or no route found) - the caller always falls back to letting the amount
    be entered by hand."""
    if not ORS_API_KEY or len(waypoints) < 2:
        return None
    try:
        response = requests.post(
            ORS_DIRECTIONS_URL,
            headers={"Authorization": ORS_API_KEY, "Content-Type": "application/json"},
            json={"coordinates": [[lng, lat] for lat, lng in waypoints]},
            timeout=15,
        )
        response.raise_for_status()
        meters = response.json()["features"][0]["properties"]["summary"]["distance"]
        return round(meters / 1000, 2)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
