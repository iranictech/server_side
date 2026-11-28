"""Zenodo Production API client. Publication is disabled."""
from identifiers.zenodo_sandbox import Draft, ZenodoError
from dataclasses import dataclass
from datetime import date
from pathlib import PurePath
from urllib.parse import quote, urlparse
import os
import requests
PRODUCTION_ORIGIN = 'https://zenodo.org'
DEPOSITIONS_URL = PRODUCTION_ORIGIN + '/api/deposit/depositions'

def _production_url(url):
    """Reject redirected or API-returned URLs outside the Zenodo sandbox."""
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'zenodo.org' or parsed.port is not None or (parsed.username is not None) or (parsed.password is not None) or (not parsed.path.startswith('/api/')) or parsed.query or parsed.fragment:
        raise ZenodoError('Zenodo returned an unsafe API URL')
    return url

def journal_article_metadata(*, title, creators, description, license_id, publication_date=None):
    """Validate the minimum metadata required by the legacy deposition API."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Article title is required')
    if not isinstance(description, str) or not description.strip():
        raise ValueError('Article abstract/description is required')
    if not isinstance(creators, (list, tuple)) or not creators:
        raise ValueError('At least one creator is required')
    cleaned_creators = []
    for creator in creators:
        if not isinstance(creator, dict) or not str(creator.get('name', '')).strip():
            raise ValueError("Each creator requires a name in 'Family, Given' format")
        clean = {'name': creator['name'].strip()}
        for optional in ('affiliation', 'orcid'):
            if creator.get(optional):
                clean[optional] = str(creator[optional]).strip()
        cleaned_creators.append(clean)
    if not isinstance(license_id, str) or not license_id.strip():
        raise ValueError('An explicitly approved article license is required')
    publication_date = publication_date or date.today()
    if isinstance(publication_date, date):
        publication_date = publication_date.isoformat()
    try:
        date.fromisoformat(publication_date)
    except (TypeError, ValueError) as exc:
        raise ValueError('publication_date must be ISO YYYY-MM-DD') from exc
    return {'upload_type': 'publication', 'publication_type': 'article', 'title': title.strip(), 'description': description.strip(), 'creators': cleaned_creators, 'publication_date': publication_date, 'access_right': 'open', 'license': license_id.strip(), 'prereserve_doi': True}

class ZenodoProductionClient:

    def __init__(self, token=None, session=None, timeout=30):
        token = token if token is not None else os.environ.get('ZENODO_PRODUCTION_TOKEN')
        if not token or not token.strip():
            raise ZenodoError('ZENODO_PRODUCTION_TOKEN is required')
        self._token = token.strip()
        self._session = session or requests.Session()
        self._timeout = timeout

    def _request(self, method, url, *, json=None, data=None):
        _production_url(url)
        try:
            response = self._session.request(method, url, headers={'Authorization': 'Bearer ' + self._token, 'User-Agent': 'Janeway-Zenodo-Production/1.0'}, json=json, data=data, timeout=self._timeout, allow_redirects=False)
        except requests.RequestException as exc:
            raise ZenodoError('Zenodo Production request failed') from exc
        if not 200 <= response.status_code < 300:
            raise ZenodoError('Zenodo Production returned HTTP %d' % response.status_code)
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            raise ZenodoError('Invalid Zenodo response') from exc

    def create_draft(self, metadata):
        import re
        if not isinstance(metadata, dict):
            raise ValueError('Invalid metadata')
        metadata = dict(metadata)
        existing_doi = metadata.get('doi')
        if existing_doi:
            if not isinstance(existing_doi, str):
                raise ValueError('Invalid existing DOI')
            if not re.fullmatch('10\\.\\d{4,9}/[^\\s]+', existing_doi):
                raise ValueError('Invalid existing DOI')
            metadata.pop('prereserve_doi', None)
        else:
            metadata.pop('doi', None)
            metadata['prereserve_doi'] = True
        obj = self._request('POST', DEPOSITIONS_URL, json={'metadata': metadata})
        try:
            deposition_id = obj['id']
            remote_metadata = obj['metadata']
            if existing_doi:
                doi = remote_metadata.get('doi')
                if doi != existing_doi:
                    raise ZenodoError('Existing DOI mismatch')
            else:
                doi = remote_metadata['prereserve_doi']['doi']
            bucket_url = _production_url(obj['links']['bucket'])
            html_url = obj['links']['html']
            if type(deposition_id) is not int or deposition_id <= 0:
                raise ZenodoError('Invalid deposition ID')
            if not isinstance(doi, str) or not re.fullmatch('10\\.\\d{4,9}/[^\\s]+', doi):
                raise ZenodoError('Invalid DOI response')
            expected_url = PRODUCTION_ORIGIN + '/deposit/' + str(deposition_id)
            if html_url != expected_url:
                raise ZenodoError('Invalid draft URL')
        except (KeyError, TypeError, ValueError):
            raise ZenodoError('Production draft response is incomplete') from None
        return Draft(deposition_id, doi, bucket_url, html_url)

    def upload_pdf(self, draft, fileobj, filename):
        """Stream PDF to the draft bucket; never sends local filesystem paths."""
        if not isinstance(draft, Draft):
            raise TypeError('A known draft is required')
        name = PurePath(filename).name
        if name != filename or not name.lower().endswith('.pdf') or name in {'.', '..'}:
            raise ValueError('A plain PDF filename is required')
        bucket = _production_url(draft.bucket_url).rstrip('/')
        return self._request('PUT', bucket + '/' + quote(name, safe=''), data=fileobj)

    def get_deposition(self, deposition_id):
        """Read a remote sandbox deposition."""
        if type(deposition_id) is not int or deposition_id <= 0:
            raise ValueError('A positive deposition ID is required')
        obj = self._request('GET', DEPOSITIONS_URL + '/' + str(deposition_id))
        if not isinstance(obj, dict) or obj.get('id') != deposition_id:
            raise ZenodoError('Unexpected deposition response')
        return obj

    def list_depositions(self):
        """Read the first page of sandbox depositions."""
        obj = self._request('GET', DEPOSITIONS_URL)
        if not isinstance(obj, list):
            raise ZenodoError('Unexpected deposition list response')
        return obj

    def publish(self, draft, *, confirmed=False):
        from django.conf import settings

        if not getattr(
            settings,
            "ZENODO_PRODUCTION_PUBLISH_ENABLED",
            False,
        ):
            raise ZenodoError("Production publication is disabled")

        if confirmed is not True:
            raise ZenodoError("Explicit confirmation required")

        if not isinstance(draft, Draft):
            raise ZenodoError("Valid draft required")

        if type(draft.deposition_id) is not int:
            raise ZenodoError("Invalid deposition ID")

        if draft.deposition_id <= 0:
            raise ZenodoError("Invalid deposition ID")

        if draft.html_url != (
            PRODUCTION_ORIGIN + "/deposit/"
            + str(draft.deposition_id)
        ):
            raise ZenodoError("Invalid Production draft")

        return self._request(
            "POST",
            DEPOSITIONS_URL + "/"
            + str(draft.deposition_id)
            + "/actions/publish",
        )
