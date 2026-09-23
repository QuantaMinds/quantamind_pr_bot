# The HTTP API

**Every endpoint this product serves, what it answers, and what it refuses.** There are eight
paths and one of them is a catch-all. If a route is not listed here it does not exist, and the
endpoint answers `404 {"error": "no such path"}` rather than closing the socket.

**Who serves it.** `quantamind serve` binds `src/quantamind/serve/listener.py`, a `http.server`
handler. `POST /webhook` and `GET /health` are answered in the listener; every other GET is handed
to `src/quantamind/serve/web/routes.py`, which builds a `Reply` rather than writing to a socket so
a forged callback can be tested without one.

> **`http.server` IS NOT A HARDENED EDGE.** No TLS, no rate limiting, no slow-loris defence. It
> runs behind a reverse proxy, and nothing in CI can assert that it does — the startup banner says
> so on every boot because that is the only place an operator reliably reads.

**Two conventions hold across every route.** A JSON route always answers JSON, including on error,
so a client never has to guess whether a body is a message or markup. And **an unhandled exception
answers `500` with the exception type**, because the stdlib handler's default is to drop the
connection — which GitHub records as a failed delivery with no status, the least diagnosable
outcome there is.

---

## Contents

| Path | Method | Auth | Answers |
|---|---|---|---|
| [`/webhook`](#post-webhook) | POST | HMAC signature | JSON |
| [`/health`](#get-health) | GET | none | JSON |
| [`/provision/{tier}`](#post-provisionfree--team--enterprise) | POST | bearer token | JSON |
| [`/entitlement`](#post-entitlement) | POST | bearer token | JSON |
| [`/scan`](#get-scanrepoownername) | GET | session cookie | JSON |
| [`/`](#get--the-dashboard-index) | GET | session cookie | HTML |
| [`/r/<owner>/<name>`](#get-rownername) | GET | session cookie | HTML |
| [`/login`](#get-login) | GET | none | 302 |
| [`/callback`](#get-callback) | GET | state cookie | 302 |
| anything else | any | — | `404` |

---

## `POST /webhook`

**The only thing that starts a review.** We do not poll and we do not crawl; if GitHub does not
tell us, nothing happens.

### Request

| Header | Required | Purpose |
|---|---|---|
| `X-Hub-Signature-256` | **yes** | `sha256=<64 hex chars>`, HMAC of the raw body with the shared secret |
| `X-GitHub-Event` | yes | `pull_request`, `installation`, `installation_repositories`, or anything else |
| `X-GitHub-Delivery` | yes | GitHub's delivery GUID. **This is the replay key** |
| `Content-Length` | **yes** | Refused without it. Capped at **25 MB**, GitHub's documented maximum |

Body: GitHub's webhook payload, as raw bytes.

```bash
curl -X POST http://127.0.0.1:7331/webhook \
  -H "X-GitHub-Event: pull_request" \
  -H "X-GitHub-Delivery: 7f3a…" \
  -H "X-Hub-Signature-256: sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)" \
  -H "Content-Type: application/json" \
  --data "$BODY"
```

### Responses

| Status | Body | When |
|---|---|---|
| `202` | `{"accepted": "<delivery-id>", "repo": "owner/name", "pr": 57}` | Authenticated, new, reviewable. **Work happens after the answer** |
| `200` | `{"ignored": "<reason>"}` | Authenticated and not for us — a ping, a label change, a closed action |
| `200` | `{"provisioned": ["owner/name", …]}` | An `installation` event; the repositories were admitted and warmed |
| `200` | `{"replay": "<delivery-id>", "note": "already completed, not repeated"}` | This GUID already finished |
| `400` | `{"error": "<reason>"}` | The delivery ledger refused it |
| `401` | `{"error": "no signature header"}` | `X-Hub-Signature-256` absent |
| `401` | `{"error": "signature is not sha256=<64 hex chars>"}` | Header present, malformed |
| `401` | `{"error": "signature does not match the body"}` | Header well-formed, wrong |
| `404` | `{"error": "no such path"}` | POST to anything but `/webhook` |
| `411` | `{"error": "<reason>"}` | No usable `Content-Length` |
| `500` | `{"error": "TypeError: …"}` | Unhandled fault. **Answered so a redelivery retries something visible** |

### Why 202 and not 200

**GitHub requires a 2XX inside ten seconds and a clone does not finish in ten.** So the handler
claims the delivery, answers `202`, and reviews afterwards. A handler that did the work first would
time out, GitHub would redeliver, and the second delivery would start a second review of the same
commit.

### Three refusals worth understanding

**The signature is compared in constant time**, and `scripts/guard/runtime/
check_constant_time_compare.py` parses that file and fails the build unless it is. Comparing two
secrets with `==` stops at the first differing byte; anyone who can time your responses can then
guess the signature one byte at a time.

**`Rejected` has three values and they are not merged.** "No header", "malformed header" and "wrong
signature" need different answers — the first two are usually a misconfigured sender and the third
is either a rotated secret or an attack.

**A replay is answered `200`, not `409`.** GitHub retries, and a redelivery **reuses the GUID**.
`store/deliveries.py` separates `begin()` from `complete()` so an unfinished attempt is retryable
and a finished one is not.

### Which deliveries become a review

`webhook_github.interpret()` returns one of three values, and **`Ignore` is a value, not a
silence** — "nothing to do here" and "something failed and we swallowed it" must never look the same.

- **`Review`** — `X-GitHub-Event: pull_request` **and** action in `opened`, `synchronize`,
  `reopened`, `ready_for_review`
- **`Installed`** — `installation` or `installation_repositories`
- **`Ignore`** — everything else, with the reason echoed back in the body

---

## `GET /health`

**A liveness probe that fails when the store is unreachable, rather than when the process is
alive.** It opens the store, because a check whose output is identical whether the system works or
not is not a check.

```bash
curl -s http://127.0.0.1:7331/health
```

| Status | Body |
|---|---|
| `200` | `{"ok": true, "detail": "1 tenant store(s) under /data/stores readable at schema v7"}` |
| `200` | `{"ok": true, "detail": "no tenants yet under /data/stores; the root is writable at schema v7"}` |
| `503` | `{"ok": false, "detail": "no store root at /data/stores. Creating it here would make a wrong path look healthy, so this refuses instead: provision the directory as part of deployment"}` |

**No tenants is healthy and says so.** A freshly installed service has no stores and is working
perfectly; reporting that as a failure would make "nobody has installed us yet" and "our storage is
broken" the same alarm.

**It does not create the root, and that is the point.** Creating it would make a typo in
`QUANTAMIND_DATABASE_PATH` produce a fresh empty store and a healthy verdict — a process pointed at
the wrong place looking exactly like a working one. **This refusal caught a real misconfiguration
on 2026-09-11**, when a bucket was mounted at `/data` without the `stores/` prefix inside it.

---

## `POST /provision/{free,team,enterprise}`

**Validates a tier's criteria, then admits the repositories.** Intended to be called once a payment
completes.

> **NOTHING HERE READS A PAYMENT PROCESSOR.** Build rows **B3** (Stripe) and **B7** (BYOK) are
> parked. `payment_ref` is **recorded, not verified**, and every paid reply carries
> `payment_verified: false` so a caller cannot infer that we checked anything.

### Request

| | |
|---|---|
| Header | `Authorization: Bearer <QUANTAMIND_PROVISION_SECRET>` |
| Body | JSON |

```bash
curl -X POST https://your-endpoint/provision/team \
  -H "Authorization: Bearer $QUANTAMIND_PROVISION_SECRET" \
  -d '{"account":"acme","repos":["acme/api","acme/web"],"seats":12,"payment_ref":"sub_123"}'
```

| Field | Free | Team | Enterprise |
|---|:--:|:--:|:--:|
| `account` — the GitHub login the installation belongs to | ✅ | ✅ | ✅ |
| `repos` — `["owner/name", …]`, at most 200 | ✅ | ✅ | ✅ |
| `seats` — developers being billed | — | ✅ | ✅ |
| `payment_ref` — recorded, never verified | — | ✅ | ✅ |
| `org` — the organisation holding shared standards | — | — | ✅ |

**Free is the only tier with an eligibility gate**, and that is deliberate: stars, contributors,
history length, recent activity and a cap of forty places exist because we give it away. A paying
customer has already answered the question those rules ask.

**`org` is Enterprise's one code-visible difference.** SSO, a DPA, residency and an SLA are contract
terms, not validations. Inherited standards are read from an organisation's `.quantamind`
repository, so without one the feature that distinguishes the tier has nowhere to read from.

### Responses

| Status | When |
|---|---|
| **`202`** | Accepted. Repositories provisioned; **warming has not happened yet** |
| **`422`** | Not eligible. **Every** reason, never the first |
| `400` | Body is not JSON, or `repos` is not a list of strings |
| `401` | Bad or missing bearer token |
| `404` | `{"error": "no such tier"}` — an unknown segment never falls through to one we sell |
| **`503`** | `QUANTAMIND_PROVISION_SECRET` is unset. **The route refuses rather than opening** |

**202, not 200.** Warming a repository is a clone plus an index — about 31 seconds on a large one —
and no caller waits. The route validates and records synchronously and replies with what it
accepted. Same acknowledge-then-work shape as the webhook.

```jsonc
// 202
{
  "tier": "team",
  "eligible": true,
  "account": "acme",
  "provisioned": ["acme/api", "acme/web"],
  "refused": [],
  "warming": ["acme/api", "acme/web"],
  "payment_verified": false,
  "note": "payment_ref was recorded, not verified. Nothing in this product reads a payment processor…"
}
```

```jsonc
// 422
{
  "tier": "free",
  "eligible": false,
  "message": "You are not eligible for the free tier. Every reason is listed in `refused` — all of
              them, not the first, so fixing one does not earn a second refusal.",
  "provisioned": [],
  "refused": ["acme/api: 22 stars, and the free tier needs at least 1000"]
}
```

**`eligible` ships on both**, so a caller reads one key rather than inferring from the status.

### Three refusals worth understanding

**An unset secret answers `503`, not `200`.** "Not configured" and "no authentication required" are
the same code path in most handlers and must not be here — this route grants a paid tier, and an
unauthenticated POST setting `tier=enterprise` is a free upgrade for anyone who can reach the port.
The token is compared with `hmac.compare_digest`; `==` on a secret leaks it one byte at a time.

**Nothing is provisioned unless every repository passes.** A partial provision leaves a customer
paying for repositories that were not admitted, and no reply shape makes that legible.

**A repository whose eligibility could not be read is refused, not assumed eligible.** "We could not
check" and "it qualifies" must never be the same value.

### What being ineligible then means

`installations.entitled().may_review` is **False** for an installation recorded `eligible = 0`, so
the repository is not reviewed — and **the refusal is posted rather than swallowed**: the pull
request gets a comment naming the rule and the way past it. `eligible IS NULL` — never assessed —
still reviews.

---

## `POST /entitlement`

**The billing service telling us what an account is entitled to.** `server/` owns Stripe; this
route is how the result reaches the reviewer.

**It is the only billing route this service ANSWERS, and no longer the only billing traffic.**
Since seats and credits, the reviewer also CALLS the billing service once per pull request —
`POST /billing/review/authorize` before anything is cloned, and `POST /billing/review/settle`
when the outcome is known (`ingest/billing/review_gate.py`, same bearer, `Destination.BILLING`).
What arrives here is still what that service last pushed, and it is what decides a review when the
outbound call cannot be made: see `docs/engineering/STRIPE.md`, "Seats and credits, asked on every
pull request". It writes entitlement and nothing else — no
provisioning, no warming, no clone, because a push arrives on every subscription change and a route
that cloned on each would turn a billing webhook into a fleet of git operations.

**Auth:** `Authorization: Bearer <QUANTAMIND_PROVISION_SECRET>`, compared with
`hmac.compare_digest`. The same secret `/provision/{tier}` uses — one secret, one rotation. **An
unset secret answers 503, never 200:** "not configured" and "no authentication required" must not
be the same answer.

### Request

```json
{"forge":"github","account":"acme","tier":"team","state":"active",
 "seats_included":25,"payment_ref":"sub_1234","as_of":1758067200,
 "valid_through":1760659200,"grace_until":1761868800}
```

`forge`, `account`, `tier`, `state` and `as_of` are required. **`state` must be one of `none`,
`active`, `trialing`, `past_due`, `cancelled`** — an unrecognised one is refused at the door rather
than stored, because `covering()` would read it back as `none` and silently put a paid account on
Free with a 200 already sent.

### Response — **the row is READ BACK, never echoed**

```json
{"forge":"github","account":"acme",
 "stored":{"tier":"team","state":"active","seats_included":25,
           "as_of":1758067200,"valid_through":1760659200,"grace_until":1761868800}}
```

**`stored` comes out of the database after the write, not from the request.** The store is SQLite
on a Cloud Storage FUSE mount with no file locking, and during a revision rollout two instances
briefly both write — Google's own wording is that "the last write wins and all previous writes are
lost". A push can therefore be acknowledged and then vanish. Echoing the request would confirm
nothing; echoing what the database now holds lets the caller compare and re-queue, which is exactly
what `server/src/billing/pushEntitlement.ts` does before marking a push delivered.

| status | when |
|---|---|
| 200 | recorded; `stored` carries the row as it now is |
| 400 | unreadable body, missing field, unknown `state`, or an account keyed on nothing |
| 401 | bad or missing bearer token |
| 411 | no readable body |
| 503 | `QUANTAMIND_PROVISION_SECRET` is unset — the route refuses rather than opening |

---

## `GET /scan?repo=owner/name`

**What the first history walk found for one installed repository.** It *reports* a scan; it does
not perform one — `serve/onboarding.warm()` already walks history at install time, and a clone over
HTTP would outlast any client and hand anyone who can reach the port a way to make this process
clone arbitrary repositories.

### Request

| | |
|---|---|
| Query | `repo=owner/name`, exactly as recorded at installation |
| Cookie | `qm_session=<token>` from `GET /callback` |

```bash
curl -s -H "Cookie: qm_session=$TOKEN" \
  "http://127.0.0.1:7331/scan?repo=pallets/flask"
```

### Response — `200 application/json`

```json
{
  "repo": "pallets/flask",
  "scanned": true,
  "touches": 9093,
  "files_tracked": 642,
  "newest_commit_read": "2026-02-19",
  "most_touched": [
    {"path": "flask/app.py", "touches": 354},
    {"path": "CHANGES.rst", "touches": 328},
    {"path": "CHANGES", "touches": 317},
    {"path": "flask/helpers.py", "touches": 204}
  ],
  "report": "QuantaMind -- first scan of pallets/flask\n\n9,093 file-touches across…",
  "limits": "A count of commits, not a judgement about the code. No model ran. `scanned: false` means the index is not built yet, which is not the same as a repository with no history."
}
```

| Field | Meaning |
|---|---|
| `scanned` | `false` when the index holds nothing. **A named state, not an empty table** |
| `touches` | Total `(file, commit)` pairs indexed |
| `files_tracked` | Distinct paths with at least one touch |
| `newest_commit_read` | `YYYY-MM-DD`, or `"never -- no commit was read"`. **Tells a stale index from a quiet week** |
| `most_touched` | Top ten, descending, ties broken by path |
| `report` | The same text `quantamind scan` prints — **byte-for-byte identical, verified** |
| `limits` | Ships in the payload so it cannot be separated from the numbers |

### Other responses

| Status | Body | When |
|---|---|---|
| `200` HTML | the sign-in page | No session cookie, or an expired one |
| `404` | `{"error": "no such repository"}` | Repository this account did not install, **or one that does not exist** |

**Those two are deliberately the same answer.** A 404 and a 403 together enumerate other tenants.

### What this endpoint never does

**No model runs.** The narration available at `quantamind scan --explain` has no HTTP surface, so
nothing about an installed repository is sent to a model by an HTTP request.

---

## `GET /` — the dashboard index

Lists every repository this account installed and has not removed.

| Status | Body | When |
|---|---|---|
| `200` HTML | the repository list | Signed in, at least one installation |
| `200` HTML | "No repository is installed on this account yet." | Signed in, nothing installed |
| `200` HTML | the sign-in page | Not signed in, **or the account store does not exist yet** |

**The answer comes from the installation rows, never from the path.** A browser controls the path;
it does not control what an account installed.

**A missing account store is answered, not created.** Before the first installation the file does
not exist; opening it raised into the stdlib handler and a browser got a dropped connection.
Creating it on a read would mean every visitor left a database behind.

---

## `GET /r/<owner>/<name>`

One repository's compliance table and outcome board.

| Status | Body |
|---|---|
| `200` HTML | the repository's reports |
| `404` HTML | Not found — **a repository that is not this account's answers exactly as one that does not exist** |
| `200` HTML | the sign-in page, when not signed in |

---

## `GET /login`

Starts GitHub OAuth.

| Status | Headers | When |
|---|---|---|
| `302` | `Location: <github authorize url>`, `Set-Cookie: qm_state=…` | Normal |
| `503` | — `sign-in is not configured: <reason>` | `oauth_client_id` / `oauth_client_secret` unset |

**The `state` lives in a short-lived cookie and is compared to the one in the URL** — two copies,
one the attacker cannot set. That is the double-submit pattern, and it needs no server-side table
that would then have to expire correctly. **Ten minutes**: long enough for a slow consent screen,
short enough that a stolen state value is worthless.

## `GET /callback`

Completes OAuth.

| Status | Headers / body | When |
|---|---|---|
| `302` | `Location: /`, `Set-Cookie: qm_session=…`, and `qm_state` cleared | Success |
| `400` | `sign-in failed at the <stage> step` | Any failure |

**The state cookie is spent here.** Leaving it would let one consent screen sign in twice.

**The reason is named by stage and the attacker's text is never echoed.** A callback error page
that repeats caller-supplied text is a reflection, and this one is reached by a browser.

---

## Anything else

`404`. JSON from `do_POST`, plain text from the browser routes. **Never a dropped connection** —
that is the one outcome nobody can diagnose.

---

## Deployment shapes and egress

`src/quantamind/types/deployment.py`. Every outbound call asks `permit(destination, shape)` **before
the socket opens**, and `scripts/guard/runtime/check_network_chokepoint.py` fails the build if any
module opens a socket or runs a networked git subcommand without asking.

| Shape | May reach |
|---|---|
| `cloud` | everything |
| `on_prem` | everything except Google's metadata server |
| `air_gapped` | **the clone, and nothing else** |

**Air-gapped refuses by name; it does not merely fail to connect.** A deployment with no route
produces timeouts and a late review, and the customer finds the attempt in their egress logs while
we never see it. **An outbound call that fails quietly in a bank is a finding against us, not a bug.**

**An unrecognised shape refuses rather than defaulting to `cloud`** — reading a typo as the
permissive shape is how a misconfigured air-gapped deployment starts reaching the network.

---

## Configuration read by the endpoint

Set as environment variables; `quantamind config` prints the resolved values.

| Variable | Default | Effect |
|---|---|---|
| `QUANTAMIND_WEBHOOK_SECRET` | — | **Required by `/webhook`.** The HMAC secret |
| `QUANTAMIND_PROVISION_SECRET` | — | Bearer token for `/provision/*`. **Unset refuses the routes**, it does not open them |
| `QUANTAMIND_DATABASE_PATH` | `quantamind.db` | **A root directory, not a file** — `<root>/<owner>/<name>.db` per repository |
| `QUANTAMIND_APP_ID` | — | GitHub App id |
| `QUANTAMIND_APP_KEY_PATH` | — | PEM private key, for installation tokens |
| `QUANTAMIND_POSTING_ENABLED` | `0` | `0` rehearses completely and writes nothing |
| `QUANTAMIND_INFERENCE_ENABLED` | `0` | Whether the model runs at all |
| `QUANTAMIND_INFERENCE_PROJECT` | — | GCP project for Vertex. **Empty runs no inference**, whatever `INFERENCE_ENABLED` says |
| `QUANTAMIND_MODEL` | `gemini-2.5-pro` | The model every review calls |
| `QUANTAMIND_GCLOUD_PATH` | `gcloud` | How to invoke gcloud; resolved from `PATH` unless given a path |
| `QUANTAMIND_BILLING_URL` | — | The billing service asked per pull request. **Empty is not "free for everyone"** — the cached entitlement decides |
| `QUANTAMIND_WEB_APP_URL` | `https://quantamind.co` | The site a refusal comment links to. Wrong here sends customers somewhere they cannot buy |
| `QUANTAMIND_OAUTH_CLIENT_ID` | — | Required by `/login` |
| `QUANTAMIND_OAUTH_CLIENT_SECRET` | — | Required by `/callback` |
| `QUANTAMIND_PUBLIC_READ_TOKEN` | — | Read-only token for repositories we are **not** installed on; the installation token is tried first |
| `QUANTAMIND_DEPLOYMENT_SHAPE` | `cloud` | `cloud`, `on_prem`, `air_gapped` |
| `QUANTAMIND_CLONE_ROOT` | `.quantamind-clones` | Where working clones live |
| `QUANTAMIND_MAX_REQUESTS` | `3` | Model requests per review; `0` makes every review deterministic |
| `QUANTAMIND_THRESHOLD_PERCENTILE` | `0.9` | Where a rule starts firing. Must be strictly between 0 and 1 |
| `QUANTAMIND_SUBPROCESS_TIMEOUT_SECONDS` | `30` | Ceiling on every git call |

**`POSTING_ENABLED=0` is a complete rehearsal, not a description of one.** Everything runs — clone,
API reads, ranking, rendering — and the comment is printed instead of sent. The only step not
exercised is the one that writes to someone else's project.
