▗ ▗   ▖ ▖  Claude Code v2.1.260
           Sonnet 5 · Claude Pro
  ▘▘ ▝▝    ~/code/lab37/specs


❯ We're building out the initial prototype for a Python backend and HTML/CSS    
  frontend for an order management system. The frontend should be simple HTML   
  and CSS for now. The backend should use Python with FastAPI. We need all our  
  interfaces for Python to be strictly typed. We do not need any                
  user-management or authentication for this prototype: we're just focusing on  
  order management. The system needs to handle 3 types of order ingestion: 1)   
  webhook ingestion following the schema in                                     
  /Users/nick/code/lab37/specs/webhook_orders.jsonl, 2) polling API calls       
  following the schema at /Users/nick/code/lab37/specs/api_responses.jsonl      
  where users can request recent orders using a time_since query parameter, and 
  3) CSV uploads where each line of sample data represents a single order       
  provided by a user styled after the output of a survey form following the     
  examples at /Users/nick/code/lab37/specs/orders_1.csv,                        
  /Users/nick/code/lab37/specs/orders_2.csv,                                    
  /Users/nick/code/lab37/specs/orders_3.csv,                                    
  /Users/nick/code/lab37/specs/orders_4.csv. Write a plan in                    
  /Users/nick/code/lab37/docs/plans to build the MVP for this prototype.        
  Remember that we're starting this build from scratch, and also that we have   
  specification files in the /Users/nick/code/lab37/specs directory for each of 
  the order ingestion pipelines.                                                

⏺ I'll examine the spec files first to ground the plan in the actual data
  shapes.

  Read 1 file, listed 1 directory, ran 7 shell commands (ctrl+o to expand)

⏺ Auto mode lets Claude handle permission prompts automatically — Claude
  checks each tool call for risky actions and prompt injection before 
  executing. Actions Claude identifies as safe are executed, while 
  actions Claude identifies as risky are blocked and Claude may try a 
  different approach. Ideal for long-running tasks. Claude can make 
  mistakes that allow harmful commands to run, it's recommended to only 
  use in isolated environments. Shift+Tab to change mode.

⏺ There's a homework brief PDF that likely contains the actual assignment
  requirements. Let me check it before finalizing the plan.

  Read 1 file (ctrl+o to expand)

⏺ Found the actual assignment brief in docs/homework/ (a take-home for an order
  ingestion + robot-dispatch system) plus a duplicate copy of the spec files. I
  also ran empirical checks against all four spec files to nail down parsing
  quirks before committing them to the plan — most notably that CSV item lists
  mix comma- and newline-delimiting, and one menu item ("Two eggs any style with
  bacon or sausage, hash browns, and toast") contains un-parenthesized commas,
  which means naive splitting silently corrupts data unless resolved against a
  known menu-item catalog. That finding, plus the webhook's rare update: 
  ["cancelled"] events and the polling API's item-level (not order-level) hash
  records with occasional 500/partial-data responses, all shape the plan below.

⏺ Write(~/code/lab37/docs/plans/mvp-order-management-plan.md)
  ⎿  Wrote 369 lines to ../docs/plans/mvp-order-management-plan.md
      1 # Order Management System — MVP Build Plan
      3 ## 0. Context
      4 
      5 This is the take-home brief in `docs/homework/Full Stack Software
      6 build an order ingestion + management system that merges orders f
        rom three parallel sources
        istory, and skeletons a
      8 dispatch payload for a downstream robotic assembly system. Refere
        nce schemas live in
        pecs/orders_1.csv`…`orders_4.csv`.
     … +506 lines (ctrl+o to expand)

⏺ The plan is written to docs/plans/mvp-order-management-plan.md.

  Key points worth flagging directly:

  - I found docs/homework/...pdf — the actual assignment brief — which adds
    requirements beyond your message: an order-history/event timeline per order,
    a dispatched state with a skeleton robot-assembly payload, an explicit
    fault-tolerance strategy per pipeline, and a 100k-requests/day scalability
    note. I folded all of these in since they're clearly load-bearing for what
    "MVP" means here.
  - I actually parsed all four CSVs and both JSONL files rather than guessing at
    the schema. That surfaced a real landmine: CSV items mixes comma- and
    newline-delimiting, and one menu item ("Two eggs any style with bacon or 
    sausage, hash browns, and toast") has un-parenthesized internal commas that
    a naive parser would shred into three fake items. The plan specifies a
    newline-split + paren-aware-comma-split + known-menu-catalog greedy-merge
    algorithm, verified against all 645 rows.
  - Domain model treats webhook/polling/CSV orders as genuinely separate records
    (no shared join key exists across sources in the given data) rather than
    forcing a fuzzy merge — called out explicitly as a documented non-goal, not
    silently swept under.
  - Polling orders only ever have item-level data (numeric order id, no
    customer/restaurant) per the actual api_responses.jsonl shape — the model
    reflects that instead of pretending fields exist that aren't there.

  Next step would be to start on Phase 1 (scaffolding) whenever you're ready —
  just say the word.

✻ Cogitated for 5m 7s · done 12:23 PM

※ recap: Building an MVP order management prototype (FastAPI backend, HTML/CSS frontend) per the homework brief; I just wrote the build plan to docs/plans/mvp-order-management-plan.md. Next: start Phase 1 scaffolding whenever you're ready. (disable recaps in /config)

❯ Why do we need a MealType enum?                                               

⏺ Two things drove it:

  1. It's a genuinely closed set in the real data. I confirmed meal only ever
     takes breakfast/lunch/dinner across all 645 CSV rows — unlike restaurant or
     delivery_platform, which are open-ended vendor/business data that could
     grow any time a new restaurant or delivery platform is onboarded (making
     those enums a bad fit — you'd need a code change every time). Meal service
     periods are conceptually fixed, not something new rows will introduce new
     values for.
  2. You said interfaces need to be strictly typed, and meal is one of the
     fields exposed as an API filter (GET /orders?meal=...). An enum gets
     FastAPI/Pydantic to validate that query param automatically (reject
     ?meal=brunch with a 422 instead of silently returning nothing) and shows
     the three valid options in the OpenAPI/Swagger docs for free.

  That said, the honest counter-argument: unlike OrderStatus or ItemStatus,
  MealType doesn't drive any branching logic anywhere in the system — it's
  purely descriptive/filterable. If you'd rather keep it as a plain str | None
  and skip the enum, that's a reasonable simplification and I wouldn't fight it.
  Want me to change it?

✻ Cooked for 21s · done 12:30 PM

❯ Let's keep it as-is for now.                                                  

⏺ Sounds good, no changes needed — MealType stays as an enum in the plan.

✻ Baked for 2s · done 12:34 PM

❯ As you mentioned from the homework assignemnt                                 
  (/Users/nick/code/lab37/docs/homework/Full Stack Software Engineer Homework   
  (Order v2).pdf) we need to include mocks for each of the three order          
  pipelines. How will those mocks be used to test our system?                   

⏺ Good question — the plan mentions the three mock artifacts but doesn't spell
  out how they plug into actual testing. Three distinct uses:

  1. Automated correctness tests (pytest, no network) — the normalizers/parsers
     are tested directly against the real files in specs/ (not the mock server),
     because that's deterministic and fast: feed webhook_orders.jsonl lines
     straight into the webhook normalizer and assert the upsert/cancellation
     logic; feed every orders_*.csv row into csv_item_parser.py and assert
     against the known-item catalog (this is what already caught the
     comma-parsing bug). These run in CI on every change with no moving parts.
  2. Integration tests + demo, through the actual network path — this is what
     mock_upstream/ and replay_webhook.py are for, and they test something the
     unit tests above can't: the client behavior, not just the parser. Pointing
     the real polling client at mock_upstream (which replays api_responses.jsonl
     line-by-line) lets a test assert the cursor only advances on
     200/partial-200, backs off on hard 500, and doesn't duplicate items when
     the same hash reappears with an updated status — i.e. it exercises the
     fault-tolerance logic from §3 end-to-end, not just the normalization
     function in isolation. replay_webhook.py does the same for the webhook
     path: POST every line at a running server (optionally with jitter/delay) to
     check idempotent upsert-by-order_id under repeated/bursty delivery, which
     is the "assume bursty traffic" requirement from the brief.
  3. Fault-injection scenarios specifically enabled by the mocks — because
     mock_upstream is a real (if tiny) server we control, tests can deliberately
     serve the four actual response: 500 lines from api_responses.jsonl to
     verify the poller doesn't advance its cursor and does retry with backoff,
     rather than only ever testing the happy path. Same idea for webhook: send
     malformed/incomplete payloads and confirm they're rejected with 4xx and
     logged rather than silently dropped or crashing the batch.

  The CSV pipeline is a slight variant of this: the sample CSVs already are the
  mock (no separate mock server needed), so /ingest/csv gets tested both by
  unit-testing the parser against them directly and by POSTing the actual files
  through TestClient to check the endpoint's per-row warning behavior.

  I'll add a short paragraph to the plan tying this to §8/§10 explicitly, since
  it's exactly the kind of design rationale the homework asks you to document.

  Read 1 file (ctrl+o to expand)

⏺ Update(~/code/lab37/docs/plans/mvp-order-management-plan.md)
  ⎿  Added 18 lines
      272    cursor logic, not a stub bypass.
      273  - The `/upload` page (or `curl`) against `specs/orders_1..4.cs
           v` directly.
      274  
      275 +**These aren't just demo props — they're the mechanism for tes
          +ting the fault-tolerance                                      
      276 +strategy in §3, which unit tests on the normalizers alone can'
          +t cover.** Pytest against the raw                             
      277 +`specs/` files verifies parsing/normalization correctness (det
          +erministic, no network — this is                              
      278 +what caught the CSV comma-splitting bug in §1). Testing the ac
          +tual client *behavior* — cursor                               
      279 +advancement, backoff, idempotent upserts under redelivery — ne
          +eds something that talks over                                 
      280 +HTTP, which is what `mock_upstream/` and `replay_webhook.py` a
          +re for:                                                       
      281 +                                                              
      282 +- Point the polling client at `mock_upstream` and replay it th
          +e real `response: 500` lines from                             
      283 +  `api_responses.jsonl` to assert the cursor does *not* advanc
          +e and a retry is scheduled — the                              
      284 +  sample data already contains the failure cases we need, so n
          +o synthetic fault-injection is                                
      285 +  required.                                                   
      286 +- Run `replay_webhook.py` against a live test server, includin
          +g redelivering the same lines, to                             
      287 +  assert repeated `order_id`s upsert instead of duplicating (t
          +he bursty-traffic / idempotency                               
      288 +  requirement from the brief).                                
      289 +- POST the real CSV files through `TestClient` to assert row-l
          +evel warnings surface without                                 
      290 +  failing the whole upload, using the actual ambiguous rows id
          +entified in §1 rather than                                    
      291 +  contrived ones.                                             
      292 +                                                              
      293  ## 9. Scalability notes (100,000 requests/day)
      294  
      295  That's ~1.15 req/s average with a stated bursty webhook profil
           e. For this prototype: SQLite in

⏺ Added that as a paragraph under §8, tying each mock artifact to a specific gap
  the pytest-on-raw-files approach can't cover on its own — client behavior
  (backoff, cursor advancement, idempotent redelivery) rather than just parsing
  correctness. It also notes the real 500 lines in api_responses.jsonl double as
  ready-made fault-injection cases, so no synthetic failures need to be
  invented for those tests.

✻ Cooked for 44s · done 12:36 PM

❯ /context 
  ⎿  Context Usage
     ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛀ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛁ ⛶   Sonnet 5
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   claude-sonnet-5
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   93.3k/1m tokens (9%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ 
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   Estimated usage by category
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ System prompt: 6.6k tokens (0.7%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ System tools: 28.9k tokens (2.9%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ Skills: 2.9k tokens (0.3%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶   ⛁ Messages: 54.9k tokens (5.5%)
     ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛶ ⛝ ⛝ ⛝ ⛝ ⛝ ⛝ ⛝   ⛶ Free space: 873.7k (87.4%)
                                               ⛝ Autocompact buffer: 33k tokens (3.3%)

     Auto-compact window: 1m tokens

     MCP tools · /mcp (loaded on-demand)
     └ 2 tools · 0 tokens

     Skills · /skills
     └ 18 skills · 2.9k tokens

     /context all to expand

❯ For the frontend design, we want to match the aesthetic of                    
  https://www.lab37.us/bowlbuilder/software                                     

⏺ Let me pull the actual page and its stylesheet so I get concrete colors/fonts
  rather than a vague description.

  Ran 1 shell command (ctrl+o to expand)

⏺ Fetch(https://www.lab37.us/bowlbuilder/software)
  ⎿  Received 1023 bytes (200 OK)

⏺ WebFetch only gives me text content, not actual visual styling. Let me use the
  browser automation skill to actually see the page.

⏺ Skill(claude-in-chrome)
  ⎿  Successfully loaded skill

  Called claude-in-chrome 13 times (ctrl+o to expand)

⏺ Update(~/code/lab37/docs/plans/mvp-order-management-plan.md)  ⎿  Added 37 lines
      250  one shared stylesheet, minimal vanilla JS only for the upload 
           form and the manual poll-trigger
      251  button.
      252  
      253 +**Visual direction**, matched to `lab37.us/bowlbuilder/softwar
          +e` (inspected directly —                                      
      254 +computed styles + screenshots, not guessed). That site is near
          +-monochrome and low-chroma on                                 
      255 +purpose, and — notably — its own product screenshots are an or
          +der/kitchen-ops dashboard, so                                 
      256 +the component patterns translate almost directly to this order
          + list rather than needing                                     
      257 +adaptation:                                                   
      258 +                                                              
      259 +- **Palette:** white/off-white page background, near-black (`#
          +0a0a0a`-ish) headline text,                                   
      260 +  mid-gray (`#9a9a9a`-ish) secondary/body text, a light-gray n
          +eutral surface (`#ececec`-ish) for                            
      261 +  cards and secondary buttons, and exactly one accent color — 
          +a blue (`#2f6df6`-ish) — reserved                             
      262 +  for a single "active/positive" signal (their `Active` and `R
          +eady` badges). Everything else                                
      263 +  stays grayscale; the plan's `OrderStatus`/`ItemStatus` badge
          +s should follow that same                                     
      264 +  discipline — one accent color for the "good" states, neutral
          + gray pills for everything else,                              
      265 +  rather than a different color per status.                   
      266 +- **Typography:** the site uses paid fonts (Suisse Int'l Book 
          +for large tight-tracked headings,                             
      267 +  Switzer for body); substitute a free geometric sans with a s
          +imilar character (e.g. Inter, via                             
      268 +  Google Fonts) rather than trying to license the originals — 
          +large page/section headings with                              
      269 +  slightly tightened letter-spacing, regular-weight gray body 
          +text.                                                         
      270 +- **Buttons:** fully rounded ("pill") buttons only — solid bla
          +ck fill + white text for the                                  
      271 +  primary action (e.g. "Upload," "Trigger poll"), light-gray f
          +ill + black text for secondary                                
      272 +  actions — no visible borders, no sharp-cornered buttons.    
      273 +- **Status badges:** small rounded-full pills with a tinted ba
          +ckground and matching darker text                             
      274 +  (not solid-fill, not plain text) — e.g. their `Active` badge
          + is a soft light-blue pill with                               
      275 +  blue text. Use this exact pattern for `OrderStatus`/`ItemSta
          +tus` in the dashboard and detail                              
      276 +  view.                                                       
      277 +- **Order list rows → order table rows:** their dashboard mock
          +up's row pattern (avatar circle                               
      278 +  with a customer's initial, name + order code on the first li
          +ne, small icon+text metadata —                                
      279 +  station, item count, a "Notes" tag — on a second line, right
          +-aligned status badge, and a                                  
      280 +  secondary right-aligned line for timing/courier state) maps 
          +directly onto this system's order                             
      281 +  rows: avatar initial from `customer_first_name`, `order_id`/
          +`external_id` next to the name,                               
      282 +  item count + a "Notes" indicator (when `notes` is non-empty)
          + as the metadata line, the                                    
      283 +  `OrderStatus` badge top-right, and `created_at`/`updated_at`
          + as the secondary right-aligned                               
      284 +  line.                                                       
      285 +- **Layout:** generous whitespace, card-based content on a lig
          +ht-gray page background, rounded                              
      286 +  corners (~12–16px) throughout, a left sidebar nav pattern (t
          +heir `Menu builder` mockup) is a                              
      287 +  reasonable model for grouping this app's own nav (Orders / U
          +pload / Ingestion Activity) if a                              
      288 +  sidebar ends up reading better than a top nav once there's r
          +eal content to navigate.                                      
      289 +                                                              
      290  - `/` — orders dashboard: table of unified orders, filterable 
           by source/status/restaurant/meal,
      291    plus a small "ingestion activity" panel (last poll result, r
           ecent webhook/CSV run counts) so
      292    pipeline health is visible without an admin system.

⏺ I inspected the actual page (computed styles + zoomed screenshots, not a
  guess) and updated §7 of the plan with a concrete visual direction. The useful
  surprise: their own product screenshots embedded on that page are an
  order/kitchen-ops dashboard, so the component patterns map almost directly
  onto our order list rather than needing translation:

  - Palette: near-monochrome — white background, near-black headings, gray body
    text, light-gray card surfaces, with exactly one blue accent reserved for
    "active/positive" status badges (everything else stays neutral gray).
  - Buttons: fully rounded pills — solid black primary, light-gray secondary, no
    borders.
  - Status badges: soft tinted-background pills with matching darker text (not
    solid fill).
  - Order rows: avatar-initial circle + name/order-id, a metadata line (item
    count, notes indicator), right-aligned status badge, secondary right-aligned
    timestamp line — lifted straight from their dashboard mockup.
  - Typography uses their paid fonts (Suisse Int'l, Switzer); I noted Inter as a
    free substitute with similar character rather than trying to license the
    originals.

  That's now documented in the plan so it can guide the actual template/CSS work
  later.

✻ Cooked for 2m 26s · done 12:44 PM

※ recap: We're planning an MVP order management prototype (FastAPI backend, HTML/CSS frontend) with three ingestion pipelines. Just finished updating the plan's frontend section with a visual direction matched to lab37.us/bowlbuilder/software; next step is starting Phase 1 scaffolding whenever you're ready. (disable recaps in /config)

❯ How scalable will this system be with SQLite as the backend database?         
  Approximately how many requests per second could this system handle?          

⏺ Short answer: for the 100k-requests/day requirement in the brief, SQLite is
  comfortably fine — but the reason has a specific shape that's worth
  understanding, since it changes at a very findable ceiling.

  The actual constraint isn't SQLite's raw speed, it's that writes are strictly 
  serialized. Even in WAL mode, SQLite allows unlimited concurrent readers, but
  only one writer transaction can be in flight for the whole database file at a
  time — there's no multi-writer parallelism at all, regardless of mode. So the
  real question isn't "how fast is SQLite" but "how many single-row write
  transactions can it commit per second, one at a time."

  For small, single-row transactions (which is what every ingestion write in
  this system is — one order or one item upsert per HTTP request), realistic
  throughput with WAL mode + synchronous=NORMAL on a local SSD is roughly
  hundreds to low-thousands of writes/sec. That's a wide range because it's
  dominated by fsync behavior, not CPU: synchronous=FULL (the safer default)
  forces an fsync per commit and lands you toward the low end (tens to
  low-hundreds/sec on spinning disk, more on SSD); NORMAL relaxes that in WAL
  mode (durable against app crashes, slightly less durable against OS crashes)
  and is meaningfully faster. Batching multiple rows into one transaction is
  faster still, but a live webhook/polling endpoint naturally commits one small
  transaction per request, so that optimization doesn't apply here without
  deliberately buffering.

  Against the stated requirement: 100,000 requests/day is ~1.15 req/s average.
  Even a generous burst assumption — say 50–100x average during a spike, so on
  the order of 60–120 req/s — sits well inside that
  hundreds-to-low-thousands/sec ceiling. So for this prototype's stated scale,
  SQLite isn't the bottleneck; it has comfortable headroom.

  Where it actually breaks: not at some larger req/s number per se, but the
  moment you need genuine concurrent write parallelism — e.g., scaling out to
  multiple app server processes/machines all writing at once. SQLite has no
  answer for that; every writer, no matter how many processes, funnels through
  the same single-writer lock on one file. That's the real reason §9 of the plan
  already calls out Postgres + a queue as the upgrade path — it's not that
  SQLite gets slow, it's that it structurally can't do concurrent writes at all,
  which matters once you outgrow a single process.

  Two concrete things worth pinning down now rather than leaving implicit — I'll
  add them to §9:

  Read 1 file (ctrl+o to expand)

⏺ Update(~/code/lab37/docs/plans/mvp-order-management-plan.md)
  ⎿  Added 27 lines, removed 8 lines
      329  
      330  ## 9. Scalability notes (100,000 requests/day)
      331  
      332 -That's ~1.15 req/s average with a stated bursty webhook profil
          -e. For this prototype: SQLite in                              
      333 -WAL mode is sufficient to validate correctness at this scale, 
          -and FastAPI's async handlers keep                             
      334 -the webhook path cheap. Documented upgrade path (not built now
          -, since it's explicitly a                                     
      335 -prototype): swap SQLite for Postgres, put a queue (SQS/Kafka/R
          -edis stream) in front of the                                  
      336 -webhook handler so ingestion is decoupled from persistence and
          - bursts are absorbed rather than                              
      337 -blocking the HTTP response, and run multiple stateless FastAPI
          - workers behind a load balancer.                              
      338 -Indices needed regardless: unique `(source, external_id)` on `
          -Order`, plus indices on `status`                              
      339 -and `created_at` for the filtered list views.                 
      332 +That's ~1.15 req/s average with a stated bursty webhook profil
          +e — even a generous 50–100x burst                             
      333 +multiplier lands around 60–120 req/s. SQLite's real constraint
          + isn't raw speed, it's that                                   
      334 +**writes are strictly serialized**: WAL mode allows unlimited 
          +concurrent readers, but only one                              
      335 +writer transaction can be in flight for the whole database fil
          +e at a time, in any mode, with                                
      336 +any number of app processes. For small single-row transactions
          + — which is what every ingestion                              
      337 +write here is — WAL mode with `PRAGMA synchronous=NORMAL` real
          +istically sustains hundreds to                                
      338 +low-thousands of writes/sec on local SSD (`FULL`, the safer de
          +fault, forces an fsync per commit                             
      339 +and is meaningfully slower). That comfortably covers the requi
          +rement above, so SQLite is                                    
      340 +sufficient for this prototype's stated scale — provided two th
          +ings are actually configured, not                             
      341 +just assumed:                                                 
      342  
      343 +- `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, and a non-z
          +ero `busy_timeout` (so a write                                
      344 +  that arrives while another is committing retries instead of 
          +immediately raising "database is                              
      345 +  locked").                                                   
      346 +- The app is served as a **single process**. Running multiple 
          +`uvicorn` workers against one                                 
      347 +  SQLite file doesn't add write throughput — it only adds lock
          + contention, since every worker                               
      348 +  still funnels through the same single-writer lock. Single-pr
          +ocess async concurrency (what                                 
      349 +  FastAPI already gives you for I/O-bound work) is the right m
          +odel here; horizontal scaling is                              
      350 +  the Postgres upgrade below, not more local workers.         
      351 +                                                              
      352 +Documented upgrade path (not built now, since it's explicitly 
          +a prototype): swap SQLite for                                 
      353 +Postgres, put a queue (SQS/Kafka/Redis stream) in front of the
          + webhook handler so ingestion is                              
      354 +decoupled from persistence and bursts are absorbed rather than
          + blocking the HTTP response, and                              
      355 +run multiple stateless FastAPI workers behind a load balancer 
          +— this is the point where the                                 
      356 +upgrade is driven by SQLite's structural inability to do concu
          +rrent writes at all, not by it                                
      357 +being "too slow." Indices needed regardless: unique `(source, 
          +external_id)` on `Order`, plus                                
      358 +indices on `status` and `created_at` for the filtered list vie
          +ws.                                                           
      359 +                                                              
      360  ## 10. Tech stack
      361  
      362  - **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLModel (SQ
           LAlchemy + Pydantic) over SQLite,

⏺ §9 now documents the concrete PRAGMA settings and the single-process
  requirement, plus makes explicit that the Postgres/queue upgrade is triggered
  by SQLite's structural single-writer limit, not by it being too slow at this
  scale.

✻ Churned for 54s · done 12:55 PM