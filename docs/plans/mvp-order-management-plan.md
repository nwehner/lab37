# Order Management System — MVP Build Plan

## 0. Context

This is the take-home brief in `docs/homework/Full Stack Software Engineer Homework (Order v2).pdf`:
build an order ingestion + management system that merges orders from three parallel sources
(webhook, polling API, CSV upload), tracks status and per-order history, and skeletons a
dispatch payload for a downstream robotic assembly system. Reference schemas live in
`specs/webhook_orders.jsonl`, `specs/api_responses.jsonl`, and `specs/orders_1.csv`…`orders_4.csv`.

No user accounts or auth in this prototype — single-tenant, unauthenticated, focused entirely
on order ingestion/management.

## 1. What the spec files actually say

Empirically verified against all provided sample files (not just skimmed):

**`webhook_orders.jsonl`** — 1,004 lines, one order-creation event per line:
`order_id` (uuid4), `order_source` (`Overeats` | `DoorDrop` | `Grubstub` — the delivery
platform), `restaurant` (5 distinct names), `first_name`, `last_name`, `total` (float),
`items` (`list[str]`, name only — no per-item id/price), `notes` (str, usually empty).
2 of the 1,004 lines carry an extra `update: ["cancelled"]` field with an otherwise-identical
payload — these are **cancellation events for an already-seen `order_id`**, not new orders.
This is the "real-time / bursty" pipeline.

> **Correction (Phase 3 implementation, verified against the real file):** the 1,004 lines
> contain only **998 distinct `order_id`s**, not 1,004. Beyond the 2 documented cancellation
> lines (each referencing an `order_id` seen earlier in the file), **4 more `order_id`s each
> appear twice** as plain, non-cancellation redeliveries — genuine webhook-retry-shaped
> duplicates already present in the sample data, not something we injected for testing. Found
> by replaying the full file through `scripts/replay_webhook.py` against a live server and
> inspecting the resulting row count (998 orders, not 1,004); see the Phase 3 progress note
> below. The upsert-by-`(source, external_id)` design in §4.1 already handles this case
> correctly without modification — it was designed for redelivery in general, this just
> confirms the real corpus exercises it.

**`api_responses.jsonl`** — 100 lines, each one snapshot of a polling call:
`{"response": 200 | 500, "data": {...}, "error"?: str}`. `data` is a dict keyed by an opaque
per-item hash, not by order — each value is
`{"order": int, "name": str, "category": str, "price": float, "status": "ordered" | "processing" | "with_courier" | "delivered"}`.
There is **no customer name, restaurant, or source field** in this payload — polling-sourced
orders only ever have a numeric id and a set of priced/categorized items. The same item hash
reappears across later lines with an advanced `status`, confirming this is an item-level
status-delta feed, not a resend of the whole order. 4 of 100 lines have `response: 500`; two of
those still carry a non-empty `data` alongside `"error": "... partial data may be present"` —
polling must tolerate partial failure, not just hard failure. There are no order-level or
item-level timestamps anywhere in the payload — `time_since` is a value *we* choose to send
based on our own last-poll bookkeeping, not something we get back.

**`orders_1..4.csv`** — same header (`first_name,last_name,items,notes,tomorrow,meal`) across
all four files; `orders_2/3/4` are cumulative supersets of `orders_1` (append-only survey
export snapshots, taken at different times).

> **Correction (Phase 2 implementation, verified against the real files):** the row counts
> above were off — they were apparently counted via raw line count (`wc -l`), which
> over-counts because several rows have an embedded newline inside a quoted multi-line `items`
> field. Parsing with Python's `csv` module (which correctly treats an embedded newline inside
> quotes as part of one record) gives **75 / 114 / 189 / 267 rows** in `orders_1..4.csv`
> respectively — not up to 708 — and `orders_4.csv`'s 267 rows are the full unique corpus (each
> of `orders_1..3.csv` is confirmed to be an exact row-subset of `orders_4.csv`; see
> `backend/tests/test_csv_item_parser.py::test_orders_1_through_3_are_prefixes_covered_by_orders_4`).
> The ambiguous "Two eggs..." item (below) occurs 7 times in that corpus, not 16. This doesn't
> change the parsing approach, only the corpus-size figures.

No `order_id`, no restaurant, no total, no source. `meal` ∈ {`breakfast`,`lunch`,`dinner`};
`tomorrow` ∈ {`"true"`,`"false"`} as strings, meaning "for tomorrow" vs. "for today."

The `items` field is the hard part: it mixes two delimiter styles *within the same file*, and
a naive split is not safe. Verified by parsing all 267 unique rows across the four files against
a known-item vocabulary built from the webhook/API `items`/`name` fields:

- Most rows: comma-separated on one line (`"Fried banana, Sweet tea, Apple pie"`).
- Some rows: newline-separated within the quoted CSV field, used specifically when an item
  name itself contains a comma inside parentheses, e.g.
  `"Multigrain sandwich loaf\nMilkshakes (vanilla, chocolate, strawberry)\nPhilly cheesesteak"`.
- One menu item, **`"Two eggs any style with bacon or sausage, hash browns, and toast"`**,
  contains two commas with *no* enclosing parentheses (7 occurrences across the corpus). A
  plain "split on commas outside parens" parser silently shreds this into three garbage items.
  This can only be resolved by checking candidate splits against a known menu vocabulary — see
  §4.3.

## 2. Domain model

All three sources normalize into one schema. Source-specific fields are `Optional` rather than
forcing a lossy common subset.

```python
class IngestionSource(str, Enum):
    WEBHOOK = "webhook"
    POLLING_API = "polling_api"
    CSV_UPLOAD = "csv_upload"

class OrderStatus(str, Enum):
    RECEIVED = "received"      # default on ingestion
    IN_PREP = "in_prep"        # derived from polling item statuses, when applicable
    DISPATCHED = "dispatched"  # sent to robot assembly (see §6)
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class ItemStatus(str, Enum):  # only ever populated for polling-sourced items
    ORDERED = "ordered"
    PROCESSING = "processing"
    WITH_COURIER = "with_courier"
    DELIVERED = "delivered"

class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"

class OrderItem(SQLModel, table=True):
    id: UUID
    order_id: UUID                       # FK -> Order.id
    external_item_id: str | None         # polling API's item hash; null for webhook/csv
    name: str
    category: str | None                 # polling only
    price: float | None                  # polling only
    status: ItemStatus | None            # polling only

class Order(SQLModel, table=True):
    id: UUID
    source: IngestionSource
    external_id: str | None              # webhook order_id (uuid) or polling numeric order id
                                          # (as str); null for csv. UNIQUE with (source, external_id).
    status: OrderStatus
    delivery_platform: str | None        # webhook: order_source (Overeats/DoorDrop/Grubstub)
    restaurant: str | None               # webhook only
    customer_first_name: str | None
    customer_last_name: str | None
    notes: str | None
    total: float | None                  # webhook only (given); null otherwise
    meal: MealType | None                # csv only
    for_tomorrow: bool | None            # csv only, from `tomorrow`
    created_at: datetime
    updated_at: datetime
    items: list[OrderItem]

class OrderEventType(str, Enum):
    ORDER_RECEIVED = "order_received"
    ORDER_UPDATED = "order_updated"
    ITEM_STATUS_CHANGED = "item_status_changed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_DISPATCHED = "order_dispatched"
    INGESTION_WARNING = "ingestion_warning"  # e.g. unmatched CSV item text

class OrderEvent(SQLModel, table=True):
    id: UUID
    order_id: UUID                       # FK -> Order.id
    event_type: OrderEventType
    source: IngestionSource
    detail: dict                         # JSON snapshot/diff, human-readable message, etc.
    created_at: datetime
```

**Key decision — orders from different sources are never merged into one record.** Nothing in
any of the three schemas provides a join key across sources (webhook uses a uuid, polling uses
its own numeric id, CSV has no id at all). Treating them as one unified *type* with a
per-source identity (`source` + `external_id`) is honest to the data; silently trying to
fuzzy-match "Wade Wilson's breakfast order" across a webhook hit and a CSV row would be
guesswork and is explicitly out of scope for the MVP (documented as a "next step").

**`OrderEvent` exists specifically to satisfy** "a view of each order and a history of any
changes or events relevant to that order" — every mutation (creation, item status change,
cancellation, dispatch, CSV parse warning) appends a row here rather than only updating
current state in place.

## 3. Fault tolerance strategy (per pipeline)

- **Webhook (bursty, real-time):** The endpoint does the minimum synchronous work — validate
  the payload shape, upsert by `(source=webhook, external_id=order_id)` — and returns fast.
  Upsert is idempotent by design, so redelivery of the same `order_id` (a common webhook retry
  behavior) is safe and just appends an `ORDER_UPDATED` event rather than duplicating the
  order. A malformed payload is rejected with 4xx and logged, not silently dropped and not
  allowed to crash the batch. For a real burst profile beyond prototype scale, note the
  upgrade path in §8 (queue in front of the handler) rather than building it now.
- **Polling API (scheduled):** We track our own `last_poll_at` cursor and only advance it after
  a poll whose `response == 200` (or a `500` that still yielded usable `data`, tagged as
  partial). A `500` with no usable data does **not** advance the cursor — the next scheduled
  poll re-requests the same window, with capped exponential backoff between attempts. Partial
  data present alongside a `500` is still ingested (each item upserted individually by its
  hash id), and the run is logged as `INGESTION_WARNING` rather than silently treated as a full
  success. Because item hash ids are stable across polls, re-ingesting an overlapping window is
  naturally idempotent.
- **CSV upload:** Parsing is per-row and non-fatal — a row that can't be cleanly parsed still
  produces an `Order` with the raw item text preserved and an `INGESTION_WARNING` event, rather
  than failing the whole file. Since CSV rows carry no id, exact re-upload of an
  already-ingested file (the samples are cumulative snapshots — see §1) is *not* deduplicated
  in the MVP; this is called out explicitly in §9 as a known gap with a proposed fix
  (content-hash the row to detect exact repeats), not silently ignored.
- **Cross-cutting:** every ingestion attempt (not just failures) writes a lightweight run
  record (source, started_at, outcome, counts) so the "ingestion activity" panel in the UI
  (§7) has something real to show, and so fault patterns are visible without log-diving.

## 4. Ingestion pipeline design

### 4.1 Webhook
`POST /ingest/webhook/orders` — receives one JSON object matching `webhook_orders.jsonl`
shape. If `update` is absent: upsert `Order` by `(WEBHOOK, order_id)`, replacing fields,
appending `ORDER_RECEIVED` or `ORDER_UPDATED`. If `update == ["cancelled"]`: set
`status = CANCELLED`, append `ORDER_CANCELLED`. Items are stored as `OrderItem(name=...)` with
no price/category/id (none is given).

### 4.2 Polling API
A background poller (interval-based) calls a configured upstream URL with `?time_since=<iso8601>`
and expects the `api_responses.jsonl` shape back. For each item in `data`: upsert `OrderItem`
by `external_item_id` (the hash), upsert its parent `Order` by `(POLLING_API, str(order))` if
not already present, append `ITEM_STATUS_CHANGED` when `status` differs from what's stored.
Also exposed as `POST /ingest/poll/trigger` so a poll can be forced on demand (for demos and
tests) instead of waiting on the scheduler.

### 4.3 CSV upload
`POST /ingest/csv` (multipart file upload) — for each row, `first_name`/`last_name`/`notes`/
`meal`/`for_tomorrow` map directly; `items` is parsed as:

1. Split the raw field on newlines → candidate lines, trim, drop empties.
2. Split each line on commas that are **not** inside parentheses (paren-depth-aware) →
   candidate tokens.
3. Greedily re-merge adjacent tokens against a known-menu-item catalog (longest match first):
   if joining tokens `i..j` with `", "` matches a known item name, emit it as one item and
   advance past `j`; otherwise fall back to emitting token `i` alone and flag it with an
   `INGESTION_WARNING` (raw text preserved either way — nothing is dropped).

The catalog is a static list of known item names, built once from the union of `items` values
in `webhook_orders.jsonl` and `name` values in `api_responses.jsonl`, checked into the repo as
`backend/app/data/known_menu_items.json`. This resolves the ambiguous
`"...bacon or sausage, hash browns, and toast"` case (§1) correctly, verified against the full
267-row corpus (§1 correction) with zero remaining unmatched-item false splits — confirmed by
an actual implementation (`backend/app/ingestion/csv_item_parser.py`) and test
(`backend/tests/test_csv_item_parser.py::test_full_csv_corpus_parses_with_no_unmatched_items`),
not just estimated.

Each CSV `Order` is created fresh (no id to upsert against — see §3 for the re-upload caveat).

## 5. API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ingest/webhook/orders` | Webhook receiver |
| `POST` | `/ingest/poll/trigger` | Force an immediate poll cycle |
| `POST` | `/ingest/csv` | CSV file upload |
| `GET` | `/orders` | List orders — filter by `source`, `status`, `restaurant`, `meal`; paginated |
| `GET` | `/orders/{id}` | Order detail, including current items |
| `GET` | `/orders/{id}/events` | Order event/history timeline |
| `POST` | `/orders/{id}/dispatch` | Transition to `dispatched`, emit robot payload (§6) |
| `GET` | `/ingestion/runs` | Recent ingestion run log (per pipeline), for the activity panel |

## 6. Dispatch to robot assembly

`POST /orders/{id}/dispatch` validates the order is dispatchable (not already `dispatched`,
not `cancelled`, has ≥1 item), builds a skeleton payload, appends an `ORDER_DISPATCHED` event
with that payload as `detail`, and sets `status = DISPATCHED`:

```python
class RobotDispatchItem(BaseModel):
    name: str
    category: str | None
    quantity: int = 1

class RobotDispatchPayload(BaseModel):
    order_id: UUID
    source: IngestionSource
    restaurant: str | None
    meal: MealType | None
    requested_for: Literal["today", "tomorrow"] | None
    items: list[RobotDispatchItem]
    dispatched_at: datetime
```

No real robot integration exists in the MVP — this is intentionally a skeleton, per the brief.
The endpoint returns the payload it would send; a follow-up could POST it to an actual robot
control API.

## 7. Frontend (plain HTML/CSS)

Server-rendered via FastAPI + Jinja2 (no SPA framework, per "simple HTML and CSS for now"),
one shared stylesheet, minimal vanilla JS only for the upload form and the manual poll-trigger
button.

**Visual direction**, matched to `lab37.us/bowlbuilder/software` (inspected directly —
computed styles + screenshots, not guessed). That site is near-monochrome and low-chroma on
purpose, and — notably — its own product screenshots are an order/kitchen-ops dashboard, so
the component patterns translate almost directly to this order list rather than needing
adaptation:

- **Palette:** white/off-white page background, near-black (`#0a0a0a`-ish) headline text,
  mid-gray (`#9a9a9a`-ish) secondary/body text, a light-gray neutral surface (`#ececec`-ish) for
  cards and secondary buttons, and exactly one accent color — a blue (`#2f6df6`-ish) — reserved
  for a single "active/positive" signal (their `Active` and `Ready` badges). Everything else
  stays grayscale; the plan's `OrderStatus`/`ItemStatus` badges should follow that same
  discipline — one accent color for the "good" states, neutral gray pills for everything else,
  rather than a different color per status.
- **Typography:** the site uses paid fonts (Suisse Int'l Book for large tight-tracked headings,
  Switzer for body); substitute a free geometric sans with a similar character (e.g. Inter, via
  Google Fonts) rather than trying to license the originals — large page/section headings with
  slightly tightened letter-spacing, regular-weight gray body text.
- **Buttons:** fully rounded ("pill") buttons only — solid black fill + white text for the
  primary action (e.g. "Upload," "Trigger poll"), light-gray fill + black text for secondary
  actions — no visible borders, no sharp-cornered buttons.
- **Status badges:** small rounded-full pills with a tinted background and matching darker text
  (not solid-fill, not plain text) — e.g. their `Active` badge is a soft light-blue pill with
  blue text. Use this exact pattern for `OrderStatus`/`ItemStatus` in the dashboard and detail
  view.
- **Order list rows → order table rows:** their dashboard mockup's row pattern (avatar circle
  with a customer's initial, name + order code on the first line, small icon+text metadata —
  station, item count, a "Notes" tag — on a second line, right-aligned status badge, and a
  secondary right-aligned line for timing/courier state) maps directly onto this system's order
  rows: avatar initial from `customer_first_name`, `order_id`/`external_id` next to the name,
  item count + a "Notes" indicator (when `notes` is non-empty) as the metadata line, the
  `OrderStatus` badge top-right, and `created_at`/`updated_at` as the secondary right-aligned
  line.
- **Layout:** generous whitespace, card-based content on a light-gray page background, rounded
  corners (~12–16px) throughout, a left sidebar nav pattern (their `Menu builder` mockup) is a
  reasonable model for grouping this app's own nav (Orders / Upload / Ingestion Activity) if a
  sidebar ends up reading better than a top nav once there's real content to navigate.

- `/` — orders dashboard: table of unified orders, filterable by source/status/restaurant/meal,
  plus a small "ingestion activity" panel (last poll result, recent webhook/CSV run counts) so
  pipeline health is visible without an admin system.
- `/orders/{id}/view` — order detail page: current fields + items + full event/history
  timeline. (Deviates from this section's original `/orders/{id}` — see the Phase 5 progress
  note below for why the page and the §5 JSON API at `/orders/{id}` couldn't share one path.)
- `/upload` — CSV upload form; on submit, shows a per-file summary (rows ingested, rows with
  warnings) rather than a bare success/fail.

## 8. Mocks for demoing/injecting data

Per the brief's "ideally there should be an easy way to inject additional orders... using
mocks," ship three concrete ways to drive the system end-to-end from the sample data with
zero external dependencies:

- A CLI/script (`backend/scripts/replay_webhook.py`) that POSTs each line of
  `specs/webhook_orders.jsonl` to `/ingest/webhook/orders`, with an optional delay to simulate
  bursty real-time traffic.
- A tiny local mock upstream (`backend/mock_upstream/`) that serves `api_responses.jsonl` back
  one line per call, so the real polling client (pointed at it via
  `POLLING_API_BASE_URL=http://localhost:.../mock`) exercises the actual HTTP + backoff +
  cursor logic, not a stub bypass.
- The `/upload` page (or `curl`) against `specs/orders_1..4.csv` directly.

**These aren't just demo props — they're the mechanism for testing the fault-tolerance
strategy in §3, which unit tests on the normalizers alone can't cover.** Pytest against the raw
`specs/` files verifies parsing/normalization correctness (deterministic, no network — this is
what caught the CSV comma-splitting bug in §1). Testing the actual client *behavior* — cursor
advancement, backoff, idempotent upserts under redelivery — needs something that talks over
HTTP, which is what `mock_upstream/` and `replay_webhook.py` are for:

- Point the polling client at `mock_upstream` and replay it the real `response: 500` lines from
  `api_responses.jsonl` to assert the cursor does *not* advance and a retry is scheduled — the
  sample data already contains the failure cases we need, so no synthetic fault-injection is
  required.
- Run `replay_webhook.py` against a live test server, including redelivering the same lines, to
  assert repeated `order_id`s upsert instead of duplicating (the bursty-traffic / idempotency
  requirement from the brief).
- POST the real CSV files through `TestClient` to assert row-level warnings surface without
  failing the whole upload, using the actual ambiguous rows identified in §1 rather than
  contrived ones.

## 9. Scalability notes (100,000 requests/day)

That's ~1.15 req/s average with a stated bursty webhook profile — even a generous 50–100x burst
multiplier lands around 60–120 req/s. SQLite's real constraint isn't raw speed, it's that
**writes are strictly serialized**: WAL mode allows unlimited concurrent readers, but only one
writer transaction can be in flight for the whole database file at a time, in any mode, with
any number of app processes. For small single-row transactions — which is what every ingestion
write here is — WAL mode with `PRAGMA synchronous=NORMAL` realistically sustains hundreds to
low-thousands of writes/sec on local SSD (`FULL`, the safer default, forces an fsync per commit
and is meaningfully slower). That comfortably covers the requirement above, so SQLite is
sufficient for this prototype's stated scale — provided two things are actually configured, not
just assumed:

- `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, and a non-zero `busy_timeout` (so a write
  that arrives while another is committing retries instead of immediately raising "database is
  locked").
- The app is served as a **single process**. Running multiple `uvicorn` workers against one
  SQLite file doesn't add write throughput — it only adds lock contention, since every worker
  still funnels through the same single-writer lock. Single-process async concurrency (what
  FastAPI already gives you for I/O-bound work) is the right model here; horizontal scaling is
  the Postgres upgrade below, not more local workers.

Documented upgrade path (not built now, since it's explicitly a prototype): swap SQLite for
Postgres, put a queue (SQS/Kafka/Redis stream) in front of the webhook handler so ingestion is
decoupled from persistence and bursts are absorbed rather than blocking the HTTP response, and
run multiple stateless FastAPI workers behind a load balancer — this is the point where the
upgrade is driven by SQLite's structural inability to do concurrent writes at all, not by it
being "too slow." Indices needed regardless: unique `(source, external_id)` on `Order`, plus
indices on `status` and `created_at` for the filtered list views.

## 10. Tech stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLModel (SQLAlchemy + Pydantic) over SQLite,
  `mypy --strict` — every function signature, model field, and API schema fully typed, no
  `Any` at ingestion boundaries.
- **Frontend:** Jinja2 templates, one static CSS file, vanilla JS for the two interactive forms.
- **Testing:** `pytest` + FastAPI `TestClient`; parsers and normalizers tested directly against
  the real files in `specs/` (not synthetic fixtures), since that's what already caught the
  comma-parsing edge case in §1.

## 11. Project structure

```
backend/
  app/
    main.py
    config.py
    db.py
    models/            # Order, OrderItem, OrderEvent, enums
    data/
      known_menu_items.json
    ingestion/
      webhook.py
      polling.py
      csv_upload.py
      csv_item_parser.py
    services/
      normalization.py
      dispatch.py
    api/
      routes/
        orders.py
        ingest.py
    templates/
      dashboard.html
      order_detail.html
      upload.html
    static/
      style.css
      app.js
  mock_upstream/
    app.py             # replays api_responses.jsonl
  scripts/
    replay_webhook.py
  tests/
    test_csv_item_parser.py
    test_webhook_ingestion.py
    test_polling_ingestion.py
    test_dispatch.py
    test_orders_api.py
  pyproject.toml
specs/                  # existing schema/sample files (already present)
docs/
  plans/
    mvp-order-management-plan.md   # this file
```

## 12. Build phases

1. **Scaffolding** — FastAPI app, SQLModel models/enums, SQLite wiring, `mypy --strict` +
   pytest configured, empty route stubs.
2. **CSV pipeline first** — it's the most self-contained (pure parsing, no HTTP client). Build
   `csv_item_parser.py` against the real `specs/orders_*.csv` files until the full corpus
   parses cleanly, then wire the upload endpoint + `/upload` page.
3. **Webhook pipeline** — ingestion endpoint, upsert-by-`order_id` logic, cancellation handling,
   `scripts/replay_webhook.py`.
4. **Polling pipeline** — `mock_upstream/`, polling client with cursor + backoff, scheduler,
   manual trigger endpoint.
5. **Orders API + dashboard** — list/detail/events endpoints, dashboard + detail templates,
   ingestion-activity panel.
6. **Dispatch** — `RobotDispatchPayload`, `/orders/{id}/dispatch`, wire into detail page.
7. **Polish** — README with run instructions, screenshots, fault-tolerance write-up folded into
   the architecture doc (this plan can seed it).

## 12a. Progress

**Phase 1 — Scaffolding: complete.**

- The dev machine had only system Python 3.9.6 and no package manager (no Homebrew,
  pyenv, asdf, mise, uv). Installed `uv` via its official installer and used it to
  install Python 3.12.14 and manage the `backend/` project (`uv init`, `uv sync`,
  `uv run`), rather than assuming a preinstalled toolchain.
- `backend/` scaffolded per §11: `pyproject.toml` (FastAPI, SQLModel, Jinja2,
  python-multipart, httpx, pydantic-settings; `mypy --strict` + pytest configured),
  full directory tree (`app/models`, `app/ingestion`, `app/services`, `app/api/routes`,
  `app/templates`, `app/static`, `app/data`, `mock_upstream/`, `scripts/`, `tests/`).
- Enums and table models from §2 implemented in `app/models/`. Two deviations from the
  §2 sketch:
  - `Order`, `OrderItem`, and `OrderEvent` live together in one module
    (`app/models/order.py`) instead of one file each, because their `Relationship`s
    reference each other in both directions. Splitting them would force a circular
    import resolved via `TYPE_CHECKING`-only imports, which is a pattern we don't use
    here — co-locating the mutually-referencing classes avoids the cycle by design.
    `IngestionRun` has no relationship back to `Order`, so it stays in its own file.
  - Added an `IngestionRun` model (not in §2's sketch) to back the `GET /ingestion/runs`
    endpoint (§5) and the "ingestion activity" panel (§7): source, started_at,
    finished_at, outcome, counts. This is the "lightweight run record" §3 describes but
    doesn't formally schema out.
- `app/db.py`: SQLite engine with `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`,
  `busy_timeout=5000` wired via a SQLAlchemy `connect` event, per §9. `init_db()`
  imports `app.models` itself so table metadata is registered regardless of which
  entrypoint calls it (app startup, a script, or a test fixture).
- All 8 endpoints from §5 stubbed in `app/api/routes/{orders,ingest}.py`, returning
  `501 Not Implemented` — routes are registered and verified against the OpenAPI spec
  to match §5's method/path table exactly, but have no logic yet.
- `tests/test_app_boots.py`: smoke tests confirming the app boots, DB tables are
  created (WAL mode confirmed), and the stub routes respond.
- Verified clean: `mypy --strict` (16 source files) and `pytest`, both passing.
- Not yet committed to git — no commits exist on `main` yet; nothing is staged until
  asked for.

Since Phase 1, two follow-up refinements landed before Phase 2 started: the API route
stubs' return types were changed from a bare `object` to real Pydantic response models
(new `app/api/schemas.py`, plus `RobotDispatchPayload`/`RobotDispatchItem` from §6 in
`app/services/dispatch.py`), and `Order`/`OrderItem`/`OrderEvent`'s mutual relationship
references were restructured to avoid `TYPE_CHECKING`-only circular imports (both
already reflected in the model/route code above).

**Phase 2 — CSV pipeline: complete.**

- `backend/scripts/build_known_menu_items.py`: one-time script that unions `items`
  from `specs/webhook_orders.jsonl` and `name` from `specs/api_responses.jsonl` into
  `backend/app/data/known_menu_items.json` (91 known items, checked in per §4.3).
- `app/ingestion/csv_item_parser.py`: implements the §4.3 algorithm — split on
  newlines, then on commas outside parentheses, then greedily re-merge tokens against
  the known-item catalog (longest match first), falling back to an unmatched/flagged
  single token when no merge matches. Verified against the corrected 267-row corpus
  (§1) with **zero unmatched items** — including all 7 occurrences of the
  no-enclosing-parens ambiguous item.
- `app/ingestion/csv_upload.py`: `ingest_csv_upload()` — per-row non-fatal ingestion
  per §3. Each row becomes an `Order` (fresh, no upsert — no id to upsert against) plus
  its `OrderItem`s, an `ORDER_RECEIVED` event, and an `INGESTION_WARNING` event per
  unmatched item or unrecognized `meal`/`tomorrow` value (raw text always preserved).
  Writes one `IngestionRun` per upload (`SUCCESS` if zero warnings, else `PARTIAL`).
  Only a file that can't be decoded or is missing the `items` column fails outright
  (`CsvIngestionError` → `400`), consistent with "non-fatal per row, not per file."
  Uses the same `Session` dependency for the whole ingest of one file, so it commits as
  one transaction.
- `POST /ingest/csv` wired to `ingest_csv_upload`; `/upload` page added
  (`app/templates/base.html` + `upload.html`, `app/static/style.css` + `app.js`)
  following §7's visual direction (Inter font, pill buttons, rounded cards, one blue
  accent). Verified in an actual browser: uploaded `specs/orders_1.csv` through the
  live form and confirmed the on-page summary (75 rows ingested, 0 warnings) matches
  the real row count.
- Tests: `test_csv_item_parser.py` (8 tests, includes the full-corpus zero-unmatched
  assertion and the `orders_1..3.csv ⊆ orders_4.csv` prefix check) and
  `test_csv_upload_ingestion.py` (3 tests: real `orders_4.csv` end-to-end via
  `TestClient`, a synthetic unmatched-item row asserting the warning event and
  non-fatal ingestion, and the missing-column rejection path). Added
  `tests/conftest.py` so the suite runs against an isolated temp SQLite file instead of
  the real dev database.
- Bug found and fixed along the way: `Order`/`OrderItem`/`OrderEvent` (from Phase 1)
  actually failed at runtime the first time a row was inserted — SQLModel's
  `Relationship()` handling needs the *real* annotation object (e.g. `list[OrderItem]`)
  to decide whether to auto-wrap it in `Mapped[...]`, and `from __future__ import
  annotations` turns that into a string first, breaking the check. Fixed by dropping
  the future-annotations import from `app/models/order.py` specifically and quoting
  the two forward references (`"OrderItem"`, `"OrderEvent"`) manually instead. Neither
  `mypy --strict` nor the Phase 1 smoke tests caught this, since nothing had exercised
  an actual insert until CSV ingestion did.
- Verified clean: `mypy --strict` (24 source files) and `pytest` (13 tests), both
  passing.

**Phase 3 — Webhook pipeline: complete.**

- `app/ingestion/webhook.py`: `ingest_webhook_order()` implements §4.1 — a
  `WebhookOrderPayload` pydantic model validates the incoming JSON shape; a
  malformed payload raises `WebhookIngestionError`, which the route maps to
  `400` (mirroring `CsvIngestionError`'s pattern), after logging a failed
  `IngestionRun` rather than silently dropping it. On a valid payload:
  upsert `Order` by `(WEBHOOK, order_id)` — a brand-new `order_id` creates
  the order plus its items and an `ORDER_RECEIVED` event; a redelivered
  `order_id` replaces the order's fields and wholesale-replaces its items
  (no per-item id to diff against) and appends `ORDER_UPDATED`; `update:
  ["cancelled"]` sets `status = CANCELLED` and appends `ORDER_CANCELLED`.
  One deviation from §4.1's literal reading: a cancellation for an
  `order_id` never seen before (not present in the sample data, but
  possible in principle since the cancellation payload carries every field
  a creation payload does) still ingests the order rather than erroring,
  since rejecting data with enough information to process would contradict
  §3's fault-tolerance intent.
- `POST /ingest/webhook/orders` wired in `app/api/routes/ingest.py`; the
  route accepts a raw `dict[str, Any]` body rather than a typed Pydantic
  request model, so shape validation happens inside
  `ingest_webhook_order()` (where it can log the `IngestionRun`) instead of
  short-circuiting to FastAPI's automatic `422` before that logging runs.
- `backend/scripts/replay_webhook.py`: CLI that POSTs each line of a
  `webhook_orders.jsonl`-shaped file to a running server, with `--delay` to
  simulate bursty traffic, `--limit` for partial replays, and `--base-url`
  to target any running instance. Verified live (not just via
  `TestClient`) against an actual `uvicorn` process: replayed all 1,004
  real lines successfully, then re-replayed the first 5 lines to confirm
  redelivery doesn't duplicate orders. This surfaced a corpus detail
  beyond §1's original characterization — of 1,004 lines there are only
  998 distinct `order_id`s: the 2 documented cancellation lines each
  reference an already-seen id (as §1 says), plus **4 more `order_id`s
  each appear twice as plain (non-cancellation) redeliveries** — real
  webhook-retry-shaped duplicates in the sample data itself, not
  synthetic. The upsert logic handles both cases identically without
  special-casing, confirmed by direct DB inspection (998 orders, exactly 2
  `CANCELLED`, first redelivered order's event history showing
  `ORDER_RECEIVED` then two `ORDER_UPDATED`s).
- Tests: `tests/test_webhook_ingestion.py` (5 tests) — new-order creation,
  redelivery-upserts-not-duplicates, cancellation-of-existing-order,
  malformed-payload-rejected-and-logged, and a full-corpus end-to-end test
  against the real `specs/webhook_orders.jsonl` asserting the order count
  matches the 998 unique ids and exactly the 2 documented ids end up
  `CANCELLED`.
- Verified clean: `mypy --strict` (20 source files) and `pytest` (18
  tests), both passing.

**Phase 4 — Polling pipeline: complete.**

- `app/ingestion/polling.py`: `poll_once(session, client)` implements §4.2 —
  for each item in the poll response's `data`, upsert `OrderItem` by
  `external_item_id` (the hash) and upsert its parent `Order` by
  `(POLLING_API, str(order))`, appending `ITEM_STATUS_CHANGED` whenever a
  new item is created or an existing one's status differs from what's
  stored. `get_last_poll_cursor()` derives the `time_since` cursor from the
  most recent `SUCCESS`/`PARTIAL` `IngestionRun` for this source, rather
  than a separate state table — consistent with how `IngestionRun` is
  already used elsewhere as the source of truth for ingestion history. Per
  §3: a `200` or a `500` that still carries non-empty `data` both ingest
  and advance the cursor (`SUCCESS` / `PARTIAL` respectively, `PARTIAL`
  carrying the upstream's `error` in the run's `message`); a `500` with no
  usable `data` ingests nothing and leaves the cursor where it was
  (`FAILURE`). `client` is an injected `httpx.AsyncClient` rather than a
  hardcoded URL specifically so tests (and the mock upstream) can exercise
  it over a real ASGI transport instead of a stubbed bypass.
- One addition beyond §4.2's literal text: `_derive_order_status()`
  recomputes the parent `Order.status` from the aggregate of its items'
  statuses after each poll (`DELIVERED` when every item is delivered,
  `IN_PREP` when any item has progressed past `ordered`, else left at
  `RECEIVED`) — this is what backs §2's `OrderStatus.IN_PREP` ("derived
  from polling item statuses, when applicable"), which §4.2 names but
  doesn't spell out the derivation rule for. It never overrides a
  `CANCELLED` or manually `DISPATCHED` order.
- `mock_upstream/app.py`: a small FastAPI app (`create_app()`, parameterized
  by a line list so tests can inject synthetic scenarios) that replays
  `specs/api_responses.jsonl` sequentially over `GET /poll` — each line's
  own `response` field becomes the actual HTTP status code of the reply
  (so a `500` line in the corpus really answers with HTTP 500 and its
  `data`/`error` body), which is what makes the polling client's
  fault-tolerance branches (§3) exercise real HTTP semantics rather than a
  fabricated shortcut. `POST /reset` rewinds its cursor, for tests that
  need to replay the same line twice.
- `PollingScheduler` (in `polling.py`) runs the interval-based background
  poller from §4.2 as an asyncio task started/stopped in `app/main.py`'s
  lifespan, gated by a new `ORDER_MGMT_POLLING_ENABLED` setting (default
  `true`) — added specifically so the test suite (`tests/conftest.py` sets
  it `false`) doesn't spin up a real background poller hitting
  `localhost:8001` during every test. On `FAILURE` it waits out
  `PollingBackoff`'s current (capped-exponential) delay instead of the
  normal interval before retrying; any other outcome resets the backoff.
  `POST /ingest/poll/trigger` wired to call `poll_once()` directly for
  on-demand polls (demos/tests), per §4.2.
- Tests: `tests/test_polling_ingestion.py` (8 tests) — new-item ingestion
  with cursor advancement, same-hash re-poll is a no-op, a status
  progression (`ordered` → `processing`) both updates the item and derives
  `Order.status = IN_PREP`, a `500` with no data fails without advancing
  the cursor, a `500` with partial data ingests and advances the cursor as
  `PARTIAL`, backoff growth/reset, and a full real-corpus run against the
  actual `specs/api_responses.jsonl` asserting the exact outcome
  breakdown (96 `SUCCESS` / 2 `PARTIAL` / 2 `FAILURE`, matching the file's
  4 `response: 500` lines — 2 with usable data and 2 without, per §1) and
  that every distinct polling `order` id ends up as one `Order` row.
- Verified live, not just via `TestClient`: ran `mock_upstream.app` and the
  real app as two separate `uvicorn` processes and called
  `POST /ingest/poll/trigger` 100 times against the real network stack.
  Outcomes matched the test suite exactly (96/2/2), and the resulting
  database held exactly 60 orders and 264 items — both independently
  confirmed against the raw file (60 distinct `order` values, 264 distinct
  item hashes across all 100 lines).
- Verified clean: `mypy --strict` (23 source files under `app/` +
  `mock_upstream/`, 32 including `tests/` and `scripts/`) and `pytest` (25
  tests), both passing.

**Phase 5 — Orders API + dashboard: complete.**

- `app/services/queries.py`: shared read-query helpers (`list_orders` with
  `source`/`order_status`/`restaurant`/`meal` filters and offset/limit
  pagination, `get_order_by_id`, `list_order_events`, `list_ingestion_runs`,
  `list_distinct_restaurants`) used by both the JSON API routes and the
  Jinja2 page handlers, so the two never duplicate query logic or make an
  HTTP call back into the same app to render a page.
- `GET /orders`, `GET /orders/{id}/events`, and `GET /ingestion/runs` wired
  in `app/api/routes/{orders,ingest}.py` per §5, replacing their `501`
  stubs; a missing order 404s rather than 200-with-null.
- One deviation from §5/§7's literal path tables, found while implementing:
  both sections name `/orders/{id}` — §5 as the JSON detail API, §7 as the
  server-rendered detail *page* — which can't both be registered as
  separate FastAPI routes (identical path + method always resolves to
  whichever is registered first, full stop; Starlette's router doesn't
  consider `Accept` at all). First tried content negotiation inside one
  handler (branch on the `Accept` header, return either the JSON model or
  a rendered template), then reconsidered: a single handler silently
  serving two different response shapes off one path is surprising to
  read and to call, and doesn't compose with `response_model` cleanly. Not
  worth it for what a rename solves outright, so the page moved instead —
  the JSON API stays at the literal `GET /orders/{id}` from §5, and the
  HTML page from §7 now lives at `GET /orders/{id}/view` (registered in
  `app/api/routes/pages.py`, not `orders.py`), two ordinary routes with no
  overlap. `GET /orders` and `GET /orders/{id}/events` had no such
  collision to begin with (the dashboard's own page lives at `/`, and
  there's no separate events page — history is embedded in the detail
  page), so they stay pure JSON and unrenamed.
- `app/web.py`: one shared `Jinja2Templates` instance, imported by both
  `app/api/routes/pages.py` handlers (`dashboard`, `order_detail_page`,
  `upload_page`), replacing `pages.py`'s previously private instance.
- `app/templates/dashboard.html` (new, served at `/` per §7) — a
  server-rendered order list (no client-side fetch/JS, per §7's "no SPA"
  direction): a `<form method="get">` of source/status/restaurant/meal
  `<select>`s re-requests `/` with those as query params, so filtering
  works with zero JavaScript; an ingestion-activity panel above it lists
  the 10 most recent `IngestionRun`s with outcome/source/counts/timestamp
  and a "Trigger poll" button. `app/templates/order_detail.html` (new)
  renders current fields, items (with category/price/status where the
  polling pipeline populated them), and the full event timeline per §7.
  Followed §7's visual direction already established in Phase 2's
  `upload.html`/`style.css` (pill buttons/badges, one blue accent reserved
  for "good" states — `success` runs and `delivered`/`dispatched` orders —
  everything else neutral gray) rather than introducing new patterns;
  added the order-list-row, ingestion-panel, filters, and detail-page
  styles to `style.css` to match.
- `app/static/app.js` restructured from one script gated on `#upload-form`
  existing (which meant nothing after it could ever run on a page without
  that element) into two independently-guarded init functions,
  `initUploadForm()` and the new `initPollTrigger()` — the latter POSTs
  `/ingest/poll/trigger` from the dashboard's button and reloads the page
  on success, satisfying §7's "minimal vanilla JS only for the upload form
  and the manual poll-trigger button."
- Verified live in an actual browser (Chrome, not just `TestClient`):
  booted the app plus `mock_upstream` as separate `uvicorn` processes,
  replayed 15 webhook orders, uploaded `specs/orders_1.csv`, and polled the
  mock upstream 5 times, then loaded `/`, filtered by `source=webhook`, and
  opened detail pages for a CSV-sourced order (name/meal/single item, no
  restaurant/total), a webhook-sourced order (restaurant/total/multi-item),
  and a polling-sourced order (no customer name — renders "Unknown" rather
  than crashing — items with category/price/status pills). Caught and
  fixed two cosmetic bugs this way that no test would have: `IngestionSource`/
  `OrderEventType` enum values rendered with a literal underscore (e.g.
  "Csv_upload", "Order_received") under the existing CSS `capitalize`
  transform, which only capitalizes the first letter — fixed by replacing
  underscores with spaces in the templates before display.
- Tests: `tests/test_orders_api.py` (11 tests) — empty list, list after
  ingestion, filtering by source/restaurant/status, JSON order detail at
  `GET /orders/{id}`, the HTML order detail page at
  `GET /orders/{id}/view`, 404 on the JSON detail, HTML detail, and events
  routes for an unknown id, event timeline ordering across a
  create-then-redeliver sequence, dashboard page rendering ingested data,
  and the ingestion-runs listing. `tests/test_app_boots.py`'s stub-route
  smoke test updated: `/orders` and `/ingestion/runs` now assert `200`
  instead of `501`, and a new assertion confirms `/orders/{id}/dispatch`
  (phase 6, not yet built) still correctly 501s.
- Verified clean: `mypy --strict` (35 source files under `app/`, `tests/`,
  `scripts/`, `mock_upstream/`) and `pytest` (36 tests), both passing.

**Phase 6 — Dispatch: complete.**

- `app/services/dispatch.py`: `dispatch_order(session, order)` implements §6 —
  rejects (`DispatchError`) an order that's already `DISPATCHED`, `CANCELLED`,
  or has zero items; otherwise builds the `RobotDispatchPayload` skeleton
  (`requested_for` derived from `for_tomorrow` when set, `None` for
  non-CSV orders that don't carry it), appends an `ORDER_DISPATCHED` event
  with the payload as `detail`, sets `status = DISPATCHED`, and commits.
  `POST /orders/{id}/dispatch` (`app/api/routes/orders.py`) replaces its
  `501` stub: 404 for an unknown order, 400 with the `DispatchError` message
  for a non-dispatchable one, else 200 with the payload.
- `order_detail.html` gained a "Dispatch to robot" button (visible only when
  `order.status` isn't already `dispatched`/`cancelled` and the order has
  items) next to the status badge, following §7's pill-button/one-accent
  pattern already used for "Trigger poll." `app/app.js` gained
  `initDispatchButton()` (same fetch-then-reload shape as
  `initPollTrigger()`, plus an inline error message on failure instead of
  the poll button's `alert()`, since a dispatch rejection has a specific
  reason worth showing).
- Verified live in an actual browser (Chrome, not `TestClient`): booted the
  app as a real `uvicorn` process, ingested a webhook order, opened its
  detail page, clicked "Dispatch to robot," and confirmed the badge flips to
  a blue `dispatched` pill, the button disappears (no longer dispatchable),
  and "Order Dispatched" appears in the history timeline — all without a
  full page navigation beyond the button's own reload. Also verified over
  raw HTTP (a second live `uvicorn` process, not just the browser): a second
  dispatch attempt on the same order 400s with "order is already
  dispatched."
- Tests: `tests/test_dispatch.py` (5 tests) — successful dispatch (status
  transition, event ordering, payload contents), rejecting an
  already-dispatched order, rejecting a cancelled order, rejecting a
  zero-item order (constructed directly via the DB session, since no real
  ingestion pipeline produces one), and 404 on a nonexistent order.
  `tests/test_app_boots.py`'s stub-route assertion updated: dispatching a
  nonexistent order now asserts `404` (real not-found handling) instead of
  the old `501` stub response.
- Verified clean: `mypy --strict` (36 source files) and `pytest` (41 tests),
  both passing.

Not started: polish (phase 7).

## 13. Explicit non-goals / open questions for "next steps"

- No cross-source order matching/deduping (e.g. linking a CSV row to a webhook order for the
  same person) — no reliable join key exists in the given schemas.
- No CSV re-upload deduplication yet (samples are cumulative snapshots); proposed fix is a
  content hash per row.
- No real robot integration — dispatch payload is generated and logged, not transmitted.
- No auth/multi-tenancy, by explicit scope of this prototype.
- Polling scheduler runs in-process (fine at prototype scale); would move to a real scheduler
  (Celery beat, cron, cloud scheduler) alongside the Postgres/queue upgrade in §9.
