# Gold Theme for Janeway

Custom journal frontend theme.

## Architecture

- Theme: gold
- Base theme: clean
- Installation fallback: OLH

## Scope

- Journal frontend templates
- Gold CSS and JavaScript
- Dynamic journal homepage elements

Do not modify the Clean theme directly.

## Generic theme installation and reuse

The Gold theme is journal-independent. It must not contain UA-specific code,
IDs, domains, or branding. For any existing or new journal, set:

- `general.journal_theme = gold`
- `general.journal_base_theme = clean`

The template override loader resolves Gold -> Clean -> OLH. Gold should NOT be
added to `CORE_THEMES` because it is a sub-theme. Theme discovery uses the
`src/themes/` folders. Keep all homepage elements in the standard Janeway
configuration; their visible content is supplied by Janeway, not hard-coded.

### Checks before publication

1. `python manage.py check` with the intended deployment settings.
2. Compile all Gold templates.
3. Build Gold assets and confirm hashes.
4. Test two journals with different names, logos, menus, and content.
5. Take a backup and document a rollback before changing any live journal theme.

Avoid claiming acceptance rates, APCs, issue frequency or review speed unless
real journal settings or verified data provide the figures. The UI's original
"Journal Finder" is not a functional semantic matching feature; the generic
homepage links to Janeway article search instead.
