"""Zenodo *sandbox-only* deposition client for the first integration phase.

No production Zenodo API, no Janeway database writes, no automatic publication.
Never place a Zenodo token in a URL or in application logs.
Official API: https://developers.zenodo.org/
"""
from dataclasses import dataclass
from datetime import date
from pathlib import PurePath
from urllib.parse import quote, urlparse
import os

import requests

SANDBOX_ORIGIN = "https://sandbox.zenodo.org"
DEPOSITIONS_URL = SANDBOX_ORIGIN + "/api/deposit/depositions"


class ZenodoError(RuntimeError):
    """Safe error: response bodies and authentication material are not logged."""


def _sandbox_url(url):
    """Reject redirected or API-returned URLs outside the Zenodo sandbox."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "sandbox.zenodo.org"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/api/")
        or parsed.query
        or parsed.fragment
    ):
        raise ZenodoError("Zenodo returned an unsafe API URL")
    return url


def journal_article_metadata(*, title, creators, description, license_id, publication_date=None):
    """Validate the minimum metadata required by the legacy deposition API."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Article title is required")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Article abstract/description is required")
    if not isinstance(creators, (list, tuple)) or not creators:
        raise ValueError("At least one creator is required")
    cleaned_creators = []
    for creator in creators:
        if not isinstance(creator, dict) or not str(creator.get("name", "")).strip():
            raise ValueError("Each creator requires a name in 'Family, Given' format")
        clean = {"name": creator["name"].strip()}
        for optional in ("affiliation", "orcid"):
            if creator.get(optional):
                clean[optional] = str(creator[optional]).strip()
        cleaned_creators.append(clean)
    if not isinstance(license_id, str) or not license_id.strip():
        raise ValueError("An explicitly approved article license is required")
    publication_date = publication_date or date.today()
    if isinstance(publication_date, date):
        publication_date = publication_date.isoformat()
    try:
        date.fromisoformat(publication_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("publication_date must be ISO YYYY-MM-DD") from exc
    return {
        "upload_type": "publication",
        "publication_type": "article",
        "title": title.strip(),
        "description": description.strip(),
        "creators": cleaned_creators,
        "publication_date": publication_date,
        "access_right": "open",
        "license": license_id.strip(),
        "prereserve_doi": True,
    }


@dataclass(frozen=True)
class Draft:
    deposition_id: int
    reserved_doi: str
    bucket_url: str
    html_url: str


class ZenodoSandboxClient:
    def __init__(self, token=None, session=None, timeout=30):
        token = token if token is not None else os.environ.get("ZENODO_SANDBOX_TOKEN")
        if not token or not token.strip():
            raise ZenodoError("ZENODO_SANDBOX_TOKEN is required")
        self._token = token.strip()
        self._session = session or requests.Session()
        self._timeout = timeout

    def _request(self, method, url, *, json=None, data=None):
        _sandbox_url(url)
        try:
            response = self._session.request(
                method, url,
                headers={
                    "Authorization": "Bearer " + self._token,
                    "User-Agent": "Janeway-Zenodo-Sandbox/0.1",
                },
                json=json, data=data,
                timeout=self._timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ZenodoError("Zenodo Sandbox request failed") from exc
        if not 200 <= response.status_code < 300:
            raise ZenodoError("Zenodo Sandbox returned HTTP %d" % response.status_code)
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            raise ZenodoError("Invalid Zenodo response") from exc

    def create_draft(self, metadata):
        """Create one remote draft; caller must persist the returned ID before retrying."""
        if not isinstance(metadata, dict) or not metadata.get("prereserve_doi"):
            raise ValueError("Metadata must request DOI reservation")
        obj = self._request("POST", DEPOSITIONS_URL, json={"metadata": metadata})
        try:
            deposition_id = int(obj["id"])
            doi = str(obj["metadata"]["prereserve_doi"]["doi"])
            bucket_url = _sandbox_url(obj["links"]["bucket"])
            html_url = str(obj["links"]["html"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ZenodoError("Draft response lacks required fields") from exc
        if deposition_id <= 0 or not doi.startswith("10.") or not html_url.startswith(SANDBOX_ORIGIN + "/"):
            raise ZenodoError("Invalid draft response")
        return Draft(deposition_id, doi, bucket_url, html_url)

    def upload_pdf(self, draft, fileobj, filename):
        """Stream PDF to the draft bucket; never sends local filesystem paths."""
        if not isinstance(draft, Draft):
            raise TypeError("A known draft is required")
        name = PurePath(filename).name
        if name != filename or not name.lower().endswith(".pdf") or name in {".", ".."}:
            raise ValueError("A plain PDF filename is required")
        bucket = _sandbox_url(draft.bucket_url).rstrip("/")
        return self._request("PUT", bucket + "/" + quote(name, safe=""), data=fileobj)


    def get_deposition(self, deposition_id):
        """Read a remote sandbox deposition."""
        if type(deposition_id) is not int or deposition_id <= 0:
            raise ValueError("A positive deposition ID is required")

        obj = self._request(
            "GET",
            DEPOSITIONS_URL + "/" + str(deposition_id),
        )
        if (
            not isinstance(obj, dict)
            or obj.get("id") != deposition_id
        ):
            raise ZenodoError("Unexpected deposition response")

        return obj

    def list_depositions(self):
        """Read the first page of sandbox depositions."""
        obj = self._request("GET", DEPOSITIONS_URL)

        if not isinstance(obj, list):
            raise ZenodoError("Unexpected deposition list response")

        return obj

    def publish(self, draft, *, confirmed=False):
        """Irreversible action: explicit confirmation required even in sandbox."""
        if not confirmed:
            raise ZenodoError("Explicit publication confirmation is required")
        if not isinstance(draft, Draft) or draft.deposition_id <= 0:
            raise ValueError("A known draft is required")
        url = DEPOSITIONS_URL + "/" + str(draft.deposition_id) + "/actions/publish"
        obj = self._request("POST", url)
        if not obj.get("submitted") or not obj.get("doi"):
            raise ZenodoError("Publication status was not confirmed by Zenodo")
        return obj["doi"], obj.get("record_url")
