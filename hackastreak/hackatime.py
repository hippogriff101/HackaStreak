from urllib.parse import quote

import requests

API_URL = "https://hackatime.hackclub.com/api/v1/users/{}/stats"


def get_stats(username):
    """Returns (status_code, data). Raises requests.RequestException on network errors."""
    r = requests.get(
        API_URL.format(quote(username, safe="")),
        headers={"accept": "application/json"},
        timeout=10,
    )
    if r.status_code != 200:
        return r.status_code, None
    return 200, r.json().get("data", {})
