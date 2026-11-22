# Janeway Google Scholar Citation Collector

An optional, standalone citation synchronization component
for Janeway journals.

## Purpose

The collector exports published article metadata from Janeway,
searches Google Scholar using the third-party `scholarly` package,
verifies candidate matches, and stores citation information in
journal-specific JSON cache files.

Google Scholar is not accessed through an official API.

## Requirements

- Janeway installation with Django
- Python 3.12 (tested with 3.12.3)
- Separate Python virtual environment for the collector
- `scholarly==1.7.11`
- systemd and flock for the provided scheduled runner
- Network access for live collection

## Installation

1. Copy this directory to an installation location, for example
   `/opt/janeway-scholar`.
2. Create a separate Python virtual environment.
3. Install dependencies using `requirements.txt`.
4. Copy `scholar.env.example` to a private environment file.
5. Set the paths and journal identifiers for your installation.
6. Create a writable cache directory for the service user.
7. Adapt the example systemd unit files to your installation.
8. Validate the configuration before enabling the timer.

Do not commit environment files containing private configuration.

## Environment variables

- JANEWAY_SRC: directory containing manage.py
- JANEWAY_PYTHON: Janeway virtual environment Python
- SCHOLAR_PYTHON: collector virtual environment Python
- GOLD_SCHOLAR_JOURNAL: Janeway journal code
- GOLD_SCHOLAR_JOURNAL_ID: Janeway journal primary key
- GOLD_SCHOLAR_CACHE_DIR: writable cache directory

The journal code and primary key must refer to the same journal.

## Commands

The cache synchronization script supports:

- `--dry-run`: calculate changes without writing cache output
- `--apply`: write the resulting cache
- `--collect --apply`: attempt live Google Scholar collection
- `--max-articles N`: limit collection attempts as implemented

The full `run_sync.sh` runner exports article metadata before
invoking cache synchronization. Consequently, using `--dry-run`
with the full runner still updates the exported input JSON file.

## Cache behavior

- Missing cache: initialize an empty cache in memory
- Existing valid cache: preserve eligible verified records
- Article identity change: invalidate previous verification
- Invalid JSON cache: stop without replacing the invalid cache
- Cache writes: use temporary files and atomic replacement

The article identity fingerprint considers title, year, DOI,
authors, and corporate-author status.

## Scheduling

Example systemd files are under `systemd/`.

The example timer runs weekly on Sunday at 03:00, with a
randomized delay of up to 15 minutes.

Adapt installation paths and service permissions before use.

## Security and limitations

- Do not publish private configurations or citation cache data.
- Do not run tests against the Production cache.
- The collector uses a third-party, unofficial Google Scholar
  access library; availability and results are not guaranteed.
- Google Scholar may restrict automated queries.
- Candidate matches require verification before citation
  counts are treated as verified.
- Offline cache tests do not validate live Scholar retrieval.
- The examples are not automatically installed or activated.

## Deployment status

The example configuration and offline cache logic have been
tested. Live collection and end-to-end deployment have not
been validated as part of this snapshot preparation.
