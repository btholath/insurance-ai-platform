# Phase 0 Research: Customer Management

**Feature**: `002-customer-management` | **Date**: 2026-08-06

All Technical Context unknowns are resolved below. Every decision is grounded
in code that already exists in this repository (Phase 1) or in the verified
shape of the source dataset, not in general best practice.

---

## 1. Soft delete: default manager excludes archived, second manager sees all

**Decision**: `Customer.objects` is a custom manager whose `get_queryset()`
filters `archived_at__isnull=True`. A second manager, `Customer.all_objects =
models.Manager()`, returns every row including archived ones. `objects` is
declared **first**, so it remains `_default_manager` and therefore what
related-object access and `dumpdata` use.

**Rationale**: FR-020 requires removal to be a reversible archival that
disappears from lists, searches, and single-record retrieval. FR-021 requires
the archived record's `client_id` to stay reserved so a re-load reconciles
against it rather than creating a duplicate.

These two requirements pull in opposite directions, and the second manager is
what resolves them. A default-excludes-archived manager **alone makes FR-021
unsatisfiable**: the loader looks a customer up by `client_id` to decide
create-vs-update, and if that lookup runs through a manager that hides archived
rows, the loader concludes the reference is free, tries to create it, and hits
the unique constraint on a row it cannot see. The failure mode is a hard
`IntegrityError` on a reference that appears unused — the most confusing
possible outcome for an operator re-running a load. So `all_objects` is not a
convenience accessor; it is the mechanism FR-021 depends on, and it is tested
as such.

The split also protects the two features that follow. Policy and Claims will
write `ForeignKey(Customer)`, and related managers use `_default_manager`.
With `objects` first, a policy pointing at an archived customer will not
surface that customer through ordinary traversal — the behavior FR-020 asks
for — without Policy having to know archival exists.

**Consequences for the API**: an archived customer returns 404 on GET, PATCH,
and DELETE for every caller, because the viewset's queryset is built from
`objects`. This satisfies FR-022 (non-disclosure) for free and needs no extra
branch. Re-deleting an archived customer is therefore a 404, not a
double-archive.

**Alternatives considered**:
- *Explicit `.alive()` on every queryset, no manager override*: more visible at
  each call site, but correctness becomes opt-in. Every future Policy and
  Claims query must remember the filter; one omission silently leaks archived
  personal data into a list response. Rejected — the failure is silent and the
  spec treats this record as a stable foundation for two dependent features.
- *Hard delete*: contradicts FR-020 and FR-021 outright. Rejected.
- *`django-safedelete` or similar*: a dependency for roughly fifteen lines of
  manager code, against a constitution that pins a deliberate stack. Rejected.

---

## 2. Client reference generation: max+1 under `select_for_update()`

**Decision**: when `client_id` is absent on create, generate it inside the
same `transaction.atomic()` block as the insert:

1. `Customer.all_objects.select_for_update()` — ordered by the **numeric
   suffix**, not the raw string — take the highest, add one, format `CL-%05d`.
2. Let the database unique constraint be the real backstop; retry once on
   `IntegrityError`.

The scan runs through `all_objects`, so an archived record's reference is
never reissued (FR-021).

**Rationale**: FR-005 requires the same format as the source dataset and no
collision with any existing reference. The source occupies `CL-00001` through
`CL-03000` contiguously, so max+1 continues one sequence with no reserved gap
and no second format to explain.

**Ordering correction**: the obvious implementation, `order_by("-client_id")`,
is a lexicographic sort on a `CharField`. It is correct only while every
reference is exactly five digits — at `CL-100000`, `"CL-99999"` still sorts
higher and the generator starts reissuing existing references, each one caught
by the unique constraint until the retry is exhausted. The failure is
data-dependent and would not appear in any test built on a 3,000-row dataset.
The plan therefore orders on the extracted numeric suffix
(`Cast(Substr("client_id", 4), IntegerField())`), which is correct at any
width. This is cheap to do now and expensive to discover later.

**On `select_for_update()` with no rows**: on an empty table there is nothing
to lock, so two concurrent first-creates can both compute `CL-00001`. The
unique constraint rejects the loser and the single retry resolves it. This is
the only case the lock does not cover, and it is covered by the constraint.

**Alternatives considered**:
- *Separate `CU-` prefix for API-created records*: zero collision risk and
  self-documenting origin, but deviates from FR-005's explicit "same format as
  the source dataset". Rejected on requirement conformance.
- *Postgres sequence seeded at 100001*: no locking, but the start value
  encodes an assumption about dataset size that lives in a migration and
  nowhere else; a 150,000-row future export would silently collide. Rejected.
- *UUID reference*: violates the `CL-#####` format requirement. Rejected.

---

## 3. Reusing the Phase 1 audit write path unchanged

**Decision**: call the existing `apps.audit.services.record_action()` inside
the same `transaction.atomic()` block as each write, following the pattern
already established in `apps/accounts/views.py`. No new audit model, no
signals, no `on_commit` hooks.

**Rationale**: FR-031 requires the customer change and its audit entry to
both succeed or both fail. `record_action()` is a plain synchronous
`AuditLog.objects.create()`, so calling it inside `atomic()` gives that
property directly — an audit insert failure rolls back the customer write.
Signals or `on_commit` would break FR-031 by construction, since the customer
change would already be committed when the audit write ran. `apps/audit/services.py`
documents this constraint explicitly, and the spec's Assumptions state that
existing mechanisms are reused rather than rebuilt.

Immutability is already enforced at two levels — `AuditLog.save()`/`delete()`
raise, and migrations `0002`/`0003` install a database trigger — so FR-032
requires no new work in this feature, only that nothing here attempts an
update.

**Action naming**: `customer.created`, `customer.updated`, `customer.deleted`,
matching the existing `user.created` / `user.updated` convention.
`target_type` is `"customers.Customer"`, matching `"accounts.User"`.

---

## 4. Auditing permission refusals (FR-030)

**Decision**: record refusals in a DRF custom exception handler registered at
`REST_FRAMEWORK["EXCEPTION_HANDLER"]`, which writes an `AuditLog` row with
`outcome="refused"` when a `PermissionDenied` or `NotFound` arises from a
customer route.

**Rationale**: FR-030 requires an audit entry when a customer operation is
refused for lack of permission. This is genuinely new — Phase 1 records
successes only, and `HasRole` returns `False` or raises `NotFound` without
logging.

The exception handler is the right seam because `HasRole` denies in two
different shapes: collection routes return `False` from `has_permission()`
(which DRF converts to 403/401 inside `APIView.initial()`), while detail
routes raise `NotFound` from `has_object_permission()` for
existence-non-disclosure. Both surface as exceptions at the handler, so one
place catches both. Putting the write inside `HasRole` instead would either
miss the `False` path or require changing a Phase 1 mechanism the spec says to
reuse unchanged.

**The `NotFound` ambiguity, and why refusals are scoped by role**: a detail
route raises `NotFound` both when a permitted user requests a genuinely absent
customer and when an unpermitted user is refused. The handler cannot
distinguish these from the exception alone. It therefore consults
`request.user`: an unauthenticated user, or one whose role is outside the
FR-024 view set, is a refusal; a permitted user hitting `NotFound` is an
ordinary miss and is not logged. Without this, every 404 on a mistyped
reference would be recorded as a permission refusal and the compliance record
would be noise.

**Non-disclosure is preserved**: the audit entry is written server-side; the
response body is untouched. `target_id` records what was requested, which is
the point of the entry.

**Alternatives considered**:
- *Log inside `HasRole`*: would change a Phase 1 mechanism shared by every
  module, and misses the `has_permission() -> False` path. Rejected.
- *Middleware on status code*: cannot distinguish a permission 403 from a
  validation 400 without re-deriving intent from the response. Rejected.

---

## 5. Validation placement: serializer and model, deliberately both

**Decision**: field rules (FR-009 – FR-013) live in the serializer as the
enforcement point for the API, **and** as `CheckConstraint`s plus `choices`
on the model for age, scores, and the three category fields.

**Rationale**: FR-038 requires the loader to apply the same rules as the API.
Two enforcement points risk drift, so the loader is built to construct the
**same serializer** rather than calling `Customer.objects.create()` directly —
one definition of validity, exercised by both paths. The database constraints
are a backstop against a future code path that bypasses the serializer
entirely; they are not the primary mechanism, and the tests assert the
serializer behavior because that is what produces the field-named error
messages FR-014 requires.

**Category values** come from the source data and are `TextChoices` on the
model: gender `Male`/`Female`/`Other`; lead source
`Agent`/`Referral`/`Social Media`/`Web`; fraud risk `Low`/`Medium`/`High`.
DRF's `ChoiceField` names the offending field in its error, satisfying FR-012.

**Age is 18–120**, not the dataset's observed 18–75, per the spec's
Assumptions — a future real policyholder must not be refused by an artifact of
this particular export.

**Scores are `DecimalField(max_digits=3, decimal_places=2, null=True)`**.
Decimal rather than float because the source has exactly two decimal places
and float equality in tests is a needless source of flakiness. `null=True`
with **no** `blank`-driven empty-string path, so an absent score is `None` and
never `0` — FR-006 requires absent to be distinguishable from zero, and the
serializer test asserts exactly that.

---

## 6. CSV loader: streaming, per-row atomic, same serializer

**Decision**: a `loadcustomers` management command taking a required
positional path argument (no default — FR-034), using `csv.DictReader` to
stream, validating each row through `CustomerSerializer`, and wrapping **each
row** in its own `transaction.atomic()`.

**Rationale**:

- *Per-row atomicity, not whole-file*: FR-039 requires reporting created,
  updated, and refused counts, which is only meaningful if valid rows persist
  while invalid ones are refused. FR-038's "no partially-valid subset is left
  behind from that run" is satisfied at row granularity — a refused row leaves
  nothing behind. A single file-wide transaction would make one bad row
  discard 2,999 good ones, which contradicts FR-039 having a nonzero refused
  count alongside nonzero created counts.
- *`update_or_create` semantics on `client_id` via `all_objects`*: gives
  FR-035 idempotency and FR-036 update-on-change in one step, and reconciles
  with archived records per FR-021.
- *`DictReader` ignores unmapped columns naturally*: FR-037 satisfied without
  code. The command reads only the nine columns it maps and never inspects
  `Policy_Type`, `Claim_Amount_USD`, etc.
- *Missing required columns fail before any write*: FR-040 requires creating
  no customers when the file lacks required columns. The command inspects
  `DictReader.fieldnames` up front and exits before the row loop.
- *`--dry-run` flag*: reports the counts without writing. Not required by any
  FR, but it is the natural way to satisfy FR-040's "fail clearly" check
  against a real file before committing to a write, and costs one branch.

**Actor attribution (FR-042)**: `record_action(actor=None, ...)` with
`context={"source": "loadcustomers", "file": <path>}`. `AuditLog.actor` is
already `null=True`, and migration `0003` explicitly relaxed the immutability
trigger to permit a null actor — Phase 1 anticipated exactly this. A null
actor with an identifying context is what FR-042 means by "identify it as a
system load rather than attributing the records to a person".

**Per-row audit volume**: a 3,000-row load writes 3,000 audit entries. That is
correct — FR-027 requires an entry per creation — and at roughly 3,000 small
inserts it is not a performance concern at this scale. A re-run on unchanged
input still writes 3,000 `customer.updated` entries, which is noisy but
truthful; suppressing no-op updates is deliberately **not** done here, because
deciding a row is unchanged requires a field-by-field comparison that FR-028
already needs for the diff, and conflating the two would be the kind of
optimization that hides a real update. Noted as a known characteristic rather
than a defect.

**Alternatives considered**:
- *`bulk_create` with `update_conflicts`*: much faster, but bypasses the
  serializer (breaking the FR-038 single-definition-of-validity property) and
  produces no per-row audit entries. Rejected — 3,000 rows do not need it.
- *A default file path*: FR-034 forbids a default that assumes a committed
  file. Rejected.

---

## 7. Search, filter, and pagination without new dependencies

**Decision**: implement search and filtering with explicit `query_params`
handling in `get_queryset()`, following the pattern already in
`apps/audit/views.py`. Pagination uses DRF's `PageNumberPagination` with
`page_size = 50`, matching `AuditPagination` and `UserListPagination`.

**Rationale**: `django-filter` is not currently a dependency, and the spec
requires three filters (FR-019) and three search fields (FR-018) — roughly
twenty lines against a new package and a constitution that pins a deliberate
stack. The existing audit view already establishes the in-repo idiom.

- *Search* (FR-018): `?search=` matches name, email, or `client_id` via
  `Q(name__icontains) | Q(email__icontains) | Q(client_id__icontains)`.
  `icontains` gives the case-insensitivity the spec requires.
- *Filters* (FR-019): `?lead_source=`, `?gender=`, `?fraud_risk_flag=`, each
  an exact match, combinable.
- *Ordering* (FR-017): `.order_by("id")` as the stable default, matching
  `UserViewSet`. Stability matters here specifically because pagination over
  3,000 records without a total order can repeat or skip rows across pages.

**Indexes** (SC-003, SC-004): `client_id` is unique and therefore indexed
automatically. `name` and `email` get explicit `db_index=True`. At 3,000 rows
Postgres may well choose a sequential scan regardless, and the sub-second and
sub-two-second targets would likely be met without any index — the indexes are
there for the dataset growing, not to pass the stated numbers.

**Honest limit**: a trailing-wildcard `icontains` (`%term%`) cannot use a
standard B-tree index. If search latency becomes a real problem at a much
larger scale, the answer is a `pg_trgm` GIN index, which needs a Postgres
extension and is out of scope here. Recorded so the index is not later
mistaken for something it is not.

---

## 8. Removing the Phase 1 placeholder

**Decision**: delete `PlaceholderView` from `apps/customers/views.py`, remove
its route from `apps/customers/urls.py`, and delete
`apps/customers/tests/test_views.py` in full, replacing it with the real
customer test modules.

**Rationale**: FR-043 requires the placeholder and the tests asserting its
response to be removed. The existing test file asserts
`{"module": "customers", "status": "placeholder"}` and covers nothing else, so
it is replaced rather than amended. SC-010 is verified by a test asserting
that `/api/customers/placeholder/` returns 404.

---

## 9. Spec defect noted: duplicate FR-013

**Observation, not a resolution**: the spec numbers two different requirements
`FR-013`. Under *Validation* it is the score-range rule (0–1 inclusive); the
Edge Cases section refers to "the removal behavior defined in FR-013", but the
actual archival requirement is **FR-020**.

This plan reads **FR-013 as the score-range rule** and **FR-020 as the
archival rule**, which is the reading consistent with the Requirements section
itself. Flagged for correction in the spec; it changes nothing in the design,
and no requirement is dropped under this reading.

---

## Resolved unknowns summary

| Unknown | Resolution |
|---|---|
| Soft-delete visibility | Default manager excludes archived; `all_objects` sees all (FR-021 depends on it) |
| Reference generation | Max+1 under `select_for_update()`, ordered on numeric suffix, unique constraint as backstop |
| Refusal auditing | DRF exception handler, scoped by requester role to avoid logging ordinary 404s |
| Validation placement | Serializer as single definition, shared with loader; DB constraints as backstop |
| Loader atomicity | Per-row `atomic()`, `update_or_create` on `client_id` through `all_objects` |
| Loader actor | `actor=None` with identifying `context` (migration 0003 already permits) |
| Search/filter | Explicit `query_params` in `get_queryset()`, no new dependency |
| Placeholder removal | View, route, and its test module deleted; 404 asserted |
