# Typography System

Single source of truth for typography roles, token values, and usage across the UI.

## Font Families

- `--font-heading`: `Poppins, sans-serif`
- `--font-mono`: `Source Code Pro, monospace`

## Size Tokens

Defined in [static/styles.css](../static/styles.css):

- `--fs-display`: `72px`
- `--fs-h1`: `32px`
- `--fs-h2`: `24px`
- `--fs-h3`: `18px`
- `--fs-h4`: `16px`
- `--fs-body`: `14px`
- `--fs-body-sm`: `13px`
- `--fs-label`: `12px`
- `--fs-xs`: `11px`

## Weight Tokens

- `--fw-light`: `300`
- `--fw-regular`: `400`
- `--fw-medium`: `500`
- `--fw-semibold`: `600`
- `--fw-bold`: `700`

## Semantic Roles

Use these role names when building or refactoring UI:

- `Title1`: `var(--fs-display)`, `var(--fw-regular)`, `var(--font-heading)`
- `Title2`: `var(--fs-h1)`, `var(--fw-medium)`, `var(--font-heading)`
- `Title3`: `var(--fs-h2)`, `var(--fw-medium|semibold)`, `var(--font-heading)`
- `Title4`: `var(--fs-h3)`, `var(--fw-medium|semibold)`, `var(--font-heading)`
- `Title5`: `var(--fs-h4)`, `var(--fw-semibold)`, `var(--font-heading)`
- `Body1`: `var(--fs-body)`, `var(--fw-regular)`, `var(--font-mono)`
- `Body2`: `var(--fs-body-sm)`, `var(--fw-regular|medium)`, `var(--font-mono)`
- `Label1`: `var(--fs-label)`, `var(--fw-medium|semibold)`, `var(--font-mono)`
- `Label2`: `var(--fs-xs)`, `var(--fw-semibold|bold)`, `var(--font-mono)`
- `Button`: `var(--fs-body|label)`, `var(--fw-semibold)`, `var(--font-mono)`

## Explicit Definitions

Use this section as the exact reference for `family`, `size`, and `weight`.

- `h1`: family `Poppins`, size `32px`, weight `500`
- `h2`: family `Poppins`, size `24px`, weight `500`
- `h3` (Title4): family `Poppins`, size `18px`, weight `500`
- `h4`: family `Poppins`, size `16px`, weight `600`
- `body1`: family `Source Code Pro`, size `14px`, weight `400`
- `body2`: family `Source Code Pro`, size `13px`, weight `400`
- `label1`: family `Source Code Pro`, size `12px`, weight `500`
- `label2`: family `Source Code Pro`, size `11px`, weight `600`
- `button`: family `Source Code Pro`, size `14px`, weight `600`

These explicit values are mirrored in semantic tokens in [static/styles.css](../static/styles.css) under `--type-*` variables.

## Current Class Mapping (Key UI)

### Dashboard

- `.dashboard-title` -> `Title1`
- `.card-header h2` -> `Title3`
- `.dashboard-metric` -> `Title2` with light weight
- `.dashboard-metric-copy` -> `Body1` mono
- `.dash-app-btn`, `.dash-seg-btn`, `.dashboard-pill` -> `Label/Button`

### Analysis

- `.ref-back` -> `Title2`
- `.ref-card-name` -> `Title3`
- `.ref-card-meta` -> `Label1`
- `.ref-card-summary-text` -> `Label1/Body2`

### Session Detail

- `.session-title` -> `Title2`
- `.session-date`, `.session-action-btn`, `.session-transcript-toggle` -> `Title4` (Poppins)
- `.session-summary` -> `Body1` mono
- `.session-sidebar-empty` -> `Body2` mono
- `.reflection-modal-title` -> `Title4` semibold/bold

### Practice

- `.practice-sidebar-title` -> `Title2`
- `.practice-detail-title` -> `Title3`
- `.practice-detail-copy`, `.practice-ai-item-copy` -> `Body1`
- `.practice-filter-btn`, `.practice-record-button` -> `Button`

### Journaling

- `.journal-sidebar-title` -> `Title2`
- `.journal-detail-title` -> `Title3`
- `.journal-copy`, `.journal-entry-field` -> `Body1`
- `.journal-save-btn` -> `Button`

### Nudges

- `.nudge-title` -> `Title2`
- `.trigger-card-title` -> `Title3`
- `.trigger-card-desc` -> `Label1`
- `.nudge-tab` -> `Title4` (Poppins)

## Normalization Rules

When touching UI code:

1. Prefer token values over hardcoded `px` for `font-size` and `font-weight`.
2. Default app controls (tabs, buttons, chips, status text) to `var(--font-mono)`.
3. Reserve `var(--font-heading)` for high-emphasis headings and major page titles.
4. If a new size is truly needed, add it once in `static/styles.css` and document it here.
5. Avoid one-off values like `11.5px`, `12.5px`, `13.5px` unless there is a hard product requirement.

## Files Updated In This Pass

- `static/styles.css` (added `--fs-h4`, `--fs-body-sm`)
- `templates/login.html` (tokenized heading/body/input/button typography)
- `templates/session.html` (replaced non-token values and aligned key body/meta styles)
- `templates/emotion_session.html` (aligned heading/body transcript typography)
- `templates/intent_session.html` (aligned heading/body transcript typography)
