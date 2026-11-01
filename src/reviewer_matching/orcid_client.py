"""Read publicly visible, verified email addresses from ORCID.

Disabled by default. Does not request private or limited-access data.
"""

import os

import requests

from .identity import normalize_orcid


ORCID_PUBLIC_API = "https://pub.orcid.org/v3.0"


def fetch_public_email(
    orcid,
    *,
    enabled=False,
    access_token=None,
    session=None,
):
    """Return email availability and source.

    External requests require explicit enabled=True and a token.
    No network request is made by default.
    """

    result = {
        "email": None,
        "source": "orcid_public_api",
        "status": "disabled",
    }

    if not enabled:
        return result

    identifier = normalize_orcid(orcid)

    if not identifier:
        result["status"] = "invalid_orcid"
        return result

    token = (
        access_token
        if access_token is not None
        else os.environ.get("ORCID_READ_PUBLIC_TOKEN", "")
    )

    if not isinstance(token, str) or not token.strip():
        result["status"] = "missing_token"
        return result

    client = session if session is not None else requests

    try:
        response = client.get(
            f"{ORCID_PUBLIC_API}/{identifier}/email",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token.strip()}",
            },
            timeout=(3, 10),
            allow_redirects=False,
        )

        response.raise_for_status()

        if not 200 <= response.status_code < 300:
            result["status"] = "unavailable"
            return result

        data = response.json()

    except (requests.RequestException, ValueError, TypeError):
        result["status"] = "unavailable"
        return result

    if not isinstance(data, dict):
        result["status"] = "unavailable"
        return result

    records = data.get("email")

    if not isinstance(records, list):
        result["status"] = "unavailable"
        return result

    verified_public = []

    for item in records:
        if not isinstance(item, dict):
            continue

        if item.get("verified") is not True:
            continue

        if str(item.get("visibility", "")).lower() != "public":
            continue

        if item.get("current") is False:
            continue

        address = item.get("email")

        if not isinstance(address, str):
            continue

        address = address.strip()

        if (
            not address
            or len(address) > 254
            or address.count("@") != 1
            or any(character.isspace() for character in address)
        ):
            continue

        verified_public.append(
            (item.get("primary") is True, address)
        )

    if not verified_public:
        result["status"] = "not_public"
        return result

    verified_public.sort(key=lambda entry: not entry[0])

    result["email"] = verified_public[0][1]
    result["status"] = "available"

    return result
