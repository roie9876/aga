# Evidence Contract (MVP) – Segment Validation

This document defines the **minimum evidence** required for the backend to mark a requirement as:

- `passed`
- `failed`
- `not_checked`

Principle: **No green without evidence.**

## Evidence item (common fields)
Each evaluation may include a list of evidence items. Minimum recommended fields:

- `evidence_type`: `dimension | text | structural_element | derived | missing`
- `value` + `unit` (when numeric)
- `text` (when based on OCR/annotation)
- `element` / `location` (free-form context)

> Note: bounding boxes are optional until the analyzer consistently returns them.

---

## Requirement 1.1 – Location / adjacency to external walls
**Goal:** Validate ממ"ד placement relative to external walls.

**MVP evidence (to mark checked):**
- A recognized room polygon/outline for the ממ"ד **and**
- At least one labeled external wall boundary **or** an explicit note/legend indicating “external wall” adjacency.

**Status rules:**
- `passed`: explicit evidence indicates compliant placement.
- `failed`: explicit evidence indicates non-compliance.
- `not_checked`: missing room/wall topology or no reliable external-wall identification.

> Current implementation note: not implemented yet in deterministic validator.

---

## Requirement 1.2 – Wall thickness (25–40 cm based on external wall count)
**Goal:** Validate thickness of applicable walls.

**Minimum evidence:**
- At least one **parseable wall thickness** measurement, with unit convertible to cm.

**Status rules (MVP):**
- `passed`: all parsed thicknesses in the segment meet the minimum threshold inferred for that segment.
- `failed`: at least one parsed thickness is below the minimum.
- `not_checked`: no walls detected or no parseable thickness values.

---

## Requirement 2.1 – Minimum room height 2.50 m
**Goal:** Validate room (not opening) height.

**Minimum evidence:**
- A parseable height dimension that is clearly **room height** (not door/window).

**Status rules (MVP):**
- `passed`: height ≥ 2.50 m.
- `failed`: height < 2.50 m **and** the exception (2.2) cannot be proven from evidence.
- `not_checked`: no room-height dimension found, or segment is not section-like.

---

## Requirement 2.2 – Exception: 2.20 m allowed (basement/addition + volume ≥ 22.5 m³)
**Goal:** Validate exception conditions.

**Minimum evidence (to mark checked):**
- Room height measurement **and**
- Evidence it is basement/addition **and**
- Room volume ≥ 22.5 m³ (or enough dimensions to compute it).

**Status rules (MVP):**
- `passed`: height ≥ 2.20 m and exception conditions are proven.
- `failed`: height < 2.20 m.
- `not_checked`: exception context/volume missing.

---

## Requirement 3.1 – Door spacing (≥90 cm inside, ≥75 cm outside)
**Goal:** Validate clearance from door/opening to perpendicular wall.

**Minimum evidence:**
- Explicit internal/external clearances **or**
- Door-adjacent clearance dimensions with enough context to map to both thresholds.

**Status rules (MVP):**
- `passed`: evidence indicates clearances satisfy ≥90 and ≥75.
- `failed`: evidence indicates at least one clearance violates the threshold.
- `not_checked`: no door detected, no reliable clearance evidence, or evidence is ambiguous.

---

## Requirement 3.2 – Window spacing (≥20 cm niches, ≥100 cm between light openings)
**Goal:** Validate window/opening distances.

**Minimum evidence:**
- A window-context annotation/dimension including explicit unit (cm / ס"מ) and a value that maps to 20 or 100 thresholds.

**Status rules (MVP):**
- `passed`: at least one explicit window-context spacing evidence is detected.
- `failed`: explicit evidence indicates a spacing smaller than required.
- `not_checked`: no window detected, or no explicit window-context spacing evidence.
