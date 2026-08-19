import os

import requests
from dotenv import load_dotenv

load_dotenv()

ORS_API_KEY = os.environ.get("ORS_API_KEY")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"


def get_driving_distance_km(origin_lat, origin_lng, dest_lat, dest_lng):
    """One-way driving distance in km via OpenRouteService, or None if it can't be
    calculated (no API key configured, network error, or no route found) - the caller
    always falls back to letting the amount be entered by hand."""
    if not ORS_API_KEY:
        return None
    try:
        response = requests.get(
            ORS_DIRECTIONS_URL,
            params={
                "api_key": ORS_API_KEY,
                "start": f"{origin_lng},{origin_lat}",
                "end": f"{dest_lng},{dest_lat}",
            },
            timeout=10,
        )
        response.raise_for_status()
        meters = response.json()["features"][0]["properties"]["summary"]["distance"]
        return round(meters / 1000, 2)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None
