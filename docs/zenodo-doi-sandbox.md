# Zenodo DOI integration — phase 1 (Sandbox only)

Base commit: `4520ab61be87df748629221324db30462796cd28`
Feature branch: `feature/zenodo-doi-sandbox`

## Current implementation
- `identifiers/zenodo_sandbox.py`: isolated API client for creating a Sandbox draft, pre-reserving a **test** DOI, uploading a PDF, and explicitly publishing a Sandbox record.
- `identifiers/tests/test_zenodo_sandbox.py`: mocked, network-free unit tests.
- No calls to Zenodo production. No automatic operations on article acceptance or publication. No changes to Janeway `Identifier.register()`, Crossref behaviour, or article DOI display.
- Requires `ZENODO_SANDBOX_TOKEN` **only when instantiating the client**. Never commit or paste credentials. Token requires `deposit:write`; publishing requires `deposit:actions`.

## Critical editorial and publication constraints
1. **No DOI duplication:** before any live journal workflow, check all `identifiers.Identifier` rows with `id_type="doi"` for the article (including disabled identifiers), its existing public metadata, and any Crossref registration attempt. Do not mint if a DOI already exists. Never silently replace a DOI.
2. **Do not assume DOI reservation is registration:** Sandbox DOI is not a production DOI. Only mark a DOI usable on a published article after Zenodo confirms successful *production* publication and reconciliation.
3. **DOI landing page:** Zenodo DOI resolves to the Zenodo record, not the Janeway article landing page. This may not meet journal indexing/publisher DOI policies. Approve this editorially before production rollout.
4. **Avoid draft duplication:** persist Zenodo deposition ID and the state transition (draft/uploaded/published) to a journal/article-scoped database model **before** enabling one-click actions. After timeouts, reconcile using the saved remote ID; do not blindly create a fresh draft.
5. **Permissions:** a journal-scoped role check is required for every mutation, including POST-only publishing. Dashboard access/active role must be checked against the actual permission implementation, not assumptions.
6. **PDF and rights:** upload only the public, final version whose license and redistribution permissions permit archiving on Zenodo. The client requires an explicit license ID and currently sets open access; a journal workflow **must map actual article licensing and access rights** and require editor confirmation before external publication.
7. **Publishing is irreversible for uploaded files:** after Zenodo publication, files cannot be modified in place; versions are new records.
8. **Security:** never log tokens, never put tokens in URL parameters. Environment variables are for Sandbox only at this stage. Keep remote and media URLs constrained to expected origins. Avoid network activity in the test suite.

## Next integration phase (not yet implemented)
- `ZenodoDeposit` journal/article-scoped model with uniqueness and state machine, remote ID, reserved DOI, metadata snapshot, PDF fingerprint, last error, and timestamps; migrations and tests.
- Author/title/abstract/ORCID/date/license mapping from actual Janeway model fields.
- Service layer, retry reconciliation, transaction-safe DOI assignment on successful confirmed publish using the existing `Identifier` model.
- Explicit dashboard preview, authorization checks, and separate actions (Create draft / Upload PDF / Publish).
- Sandbox end-to-end testing using a fresh sandbox account/token, followed by a separate approval for production activation.

## Local unit-test command
With the Janeway development environment configured:

```bash
export JANEWAY_SETTINGS_MODULE=core.janeway_global_settings
python -B src/manage.py test identifiers.tests.test_zenodo_sandbox --verbosity 2
```

These tests use mocked API responses and **do not** require any Zenodo token.

Official references:
- https://developers.zenodo.org/
- https://help.zenodo.org/docs/deposit/about-records/
