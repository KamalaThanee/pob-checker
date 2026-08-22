# Deterministic Matching Specification

## Scope

Matching runs entirely in the browser after Excel import and OCR. It does not
make an AI request. The matcher preserves each raw POB and OCR record while
adding computed status, reason, assignment, and evidence fields.

## Invariants

- One logical OCR tag can be assigned to at most one POB person.
- One POB person can receive at most one logical OCR assignment.
- Identical OCR cabin+bed/name records form one logical tag, while every source
  observation remains available as evidence.
- Ties and conflicting evidence are never resolved by array order.
- A typo can never produce `ok` and is never assigned across a wrong location.
- Manual overrides change only the effective status; computed evidence remains.

## Normalization

Cabin matching uppercases text and removes whitespace and hyphens. A normalized
cabin with one letter, digits, and bed A-D is split into cabin base and bed.

Name matching uppercases, trims, collapses whitespace, and compares tokens
without phonetic matching.

## Name evidence

### Exact

The complete normalized names are equal.

### Surname abbreviation

The first-name tokens are exactly equal and the final surname tokens are equal
or one starts with the other. The shorter surname fragment must contain at
least two characters.

A surname abbreviation can produce `ok` only at exact cabin+bed when both sides
of the match are unique and there are no competing POB or OCR candidates. A
two-letter surname fragment alone is not sufficient identity evidence.

### Conservative typo

Exactly one insertion, deletion, or substitution is allowed in one token of at
least five characters. The other identity token must be exact or use the safe
surname-abbreviation rule.

Typo evidence:

- Requires exact cabin+bed.
- Produces only `review`.
- Is not assigned if another plausible candidate conflicts.
- Is never used across a wrong bed or cabin.

### Weak evidence

First-name-only matches, first-name prefixes, and disagreeing surnames are weak.
Weak evidence cannot produce `ok` or an assignment. If weak evidence occupies
the expected location, the result is `review` for a location/name conflict.

## Assignment order

After duplicate and conflict detection, the matcher considers:

1. Exact cabin+bed with exact name.
2. Exact cabin+bed with safe surname abbreviation.
3. Same cabin with a different bed and strong name evidence.
4. Different cabin with strong name evidence.
5. Exact cabin+bed with a unique conservative typo.

Each stage assigns only mutually unique person/tag candidates. Equal candidates
become review cases without assignment.

## Status and reason codes

### OK

- `exact_location_exact_name`
- `exact_location_abbreviated_name`

### REVIEW

- `wrong_bed`
- `wrong_cabin`
- `location_name_conflict`
- `conservative_name_typo`
- `ambiguous_pob_candidates`
- `ambiguous_ocr_candidates`
- `conflicting_evidence`
- `duplicate_pob_record`
- `ocr_unavailable`
- `partial_ocr_failure`

### ABSENT

- `no_ocr_match`

`absent` means no reliable match was found in successfully processed supplied
images. It is not a claim of physical absence.

## Duplicate behavior

Identical OCR tags are grouped into one logical tag with a duplicate count and
sorted source-file list. Identical POB entries competing for that tag receive
`duplicate_pob_record`; neither row is selected. Similar POB candidates or OCR
candidates receive the appropriate ambiguity reason.

## Scan reliability

If all image OCR requests fail, otherwise-unmatched people receive
`ocr_unavailable`. If only some requests fail, otherwise-unmatched people
receive `partial_ocr_failure`. Matches supported by available evidence retain
their computed result.

## Manual overrides

The effective status is `userOverride ?? matchStatus`. Operators can override
to found or absent and restore the automatic result. A new scan clears all
overrides. Overrides do not erase the computed reason or evidence.
