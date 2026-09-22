# Stripe, end to end

**What this document is.** Where the money lives, how a payment becomes an entitlement, and what
each side of that boundary is allowed to know. It is written for somebody who joined this morning
and has never seen the code.

**Status.** Build row **B3**. The reviewer's own Stripe integration was built 2026-09-17 and
**removed 2026-09-18**; the billing service in `QuantaMind_Website/server/` owns the relationship.
Section "What was removed, and why" is the record of that decision — it is not a tidy-up note.

---

## 1. The shape of it in one picture

```
  browser            Stripe            billing service (server/)        reviewer (this repo)
  ───────            ──────            ─────────────────────────        ────────────────────
  POST /billing/checkout ──────────────────►
                     ◄── create session ────┘
  redirect ─────────► hosted page
                     customer pays
                            │
                            ├── customer.subscription.* ──► POST /billing/stripe/webhook
                            │      (signed)                      handleStripeEvent
                            │                                          │
                            │                            stripe_events  (the burn)
                            │                            subscriptions  (tier, status, period)
                            │                            entitlement_pushes (the outbox)
                            │                                          │
                            │                                   drainPushes
                            │                                          │
                            └──────────────────────────────►  POST /entitlement ───►  entitlement
                                                               (bearer)                 (SQLite)
                                                                       ◄── the row, READ BACK ──┘
```

**Two databases, one direction.** Postgres is the ledger. SQLite is a cache the reviewer reads on
every delivery. Nothing flows right-to-left except the read-back that proves a write landed.

---

## 2. Why the money is not in this service

`docs/engineering/DEPLOYMENT.md` states it plainly: this service runs at **`maxScale: 1`** because
its store is SQLite on a Cloud Storage FUSE mount, where Google's own wording is that *"the last
write wins and all previous writes are lost"*. That is:

- **fine for a cache.** A lost entitlement row is re-pushed; the outbox still holds it and
  `drainPushes` retries until the read-back agrees.
- **not fine for a ledger.** A lost `subscriptions` row is a customer who paid and has no record
  of it, and nothing anywhere would say so.

Three things also need a database this service does not have: a credit ledger that debits
transactionally, an admin console that queries revenue and churn, and per-seat accounting. And
`maxScale: 1` is a correctness setting here, not a capacity one — so billing throughput would be
capped at one instance for reasons that have nothing to do with billing.

**The cost of the split, stated.** An entitlement can be stale. `verify/paid_access.py` has a
verdict for exactly that (`STALE_RECORD`) and holds access OPEN through a grace window, because a
push that never arrived is our failure and withdrawing a paying customer's reviews to punish our
own outage is the wrong way round.

---

## 3. The account, the price, and one number that disagrees

| | value |
|---|---|
| Live account | `acct_1U9FQIGwi83EhBSF` — "QuantaMind" |
| Sandbox | `acct_1U9FQPGY5MuBVWoy` — "QuantaMind sandbox", test mode |
| API version | `2026-08-26.dahlia` — read off a real `Stripe-Version` response header, not chosen |
| Team | `price_1UGfiCGY5MuBVWoyiOyqLh6G` — **$29.00/month**, `licensed` per-unit |
| Team BYOK | `price_1UGfiPGY5MuBVWoysqh6SJD9` — **$26.00/month** |
| Credits | `price_1UGfiRGY5MuBVWoy2XXttRQy` — $1.00 one-time |

**The live account still carries a $39.00/month price** — `price_1U9FpWGwi83EhBSFIbuj2gSP` on
`prod_V9YxGzPjNwa8vQ`. Nothing in either codebase touches the live account, so archiving that
price is a deliberate act somebody has to perform in the Dashboard. Until then the live account
and the published price page disagree, and this paragraph is the record of it.

**The price is per-unit `licensed`, so the quantity IS the seat count.** Selling per-seat needs no
new price — only a quantity above 1, which checkout already sends.

**The API version is pinned on both sides.** `server/src/index.ts` passes it to the SDK
explicitly. The SDK currently defaults to the same string, so that line changes nothing today —
which is the point: left implicit, the version is decided by whatever `npm update` last installed,
and a bump silently changes the shape of every object read.

---

## 4. `current_period_end` is not where the documentation examples put it

Under `2026-08-26.dahlia` it is **absent from the subscription object entirely** and present only
on the subscription ITEM.

```jsonc
"data": { "object": {
  "status": "active",
  // no current_period_end here
  "items": { "data": [ { "quantity": 3, "current_period_end": 1792283886 } ] }
} }
```

A reader written against the top-level field — which is what every older example shows — records
NULL for every subscription that ever existed. **It did.** `server/src/billing/handleStripeEvent.ts`
read the top level until 2026-09-18; seats and status were correct throughout, so nothing looked
wrong, and `valid_through` reached the reviewer as null on every push. That made every account
look like one with no period, which `verify/paid_access.py` reads as permanently paid — and made
`STALE_RECORD` unreachable.

Confirmed against a REAL captured delivery, not inferred:
`server/test/fixtures/stripe_subscription_created.json` is an actual `customer.subscription.created`
from the sandbox, and `server/test/realDelivery.test.ts` asserts the top-level field is absent. If
Stripe ever puts it back, that test fails and the fallback in `periodEnd()` starts earning its keep.

---

## 5. The billing service — `QuantaMind_Website/server/src/billing/`

| file | owns |
|---|---|
| `handleStripeEvent.ts` | one verified event, applied exactly once |
| `entitlementBody.ts` | the push contract, in QuantaMind's vocabulary |
| `pushEntitlement.ts` | the outbox drain, and the read-back that proves delivery |
| `installLink.ts` | the single-use link that joins a payment to a forge account |
| `checkout.ts` | creating a Checkout Session |
| `githubApp.ts` | turning an `installation_id` into an account name |
| `prices.ts` | price id → tier, and whether it is BYOK |

**`customer.subscription.*` is the only authority for tier and status.** `checkout.session.completed`
links a customer to an account; neither writes a tier. Five writers to one field is five chances to
disagree.

**The burn is the first statement inside the transaction.** `INSERT INTO stripe_events … ON
CONFLICT DO NOTHING RETURNING` — a replayed event finds the row taken, writes nothing, rolls back.
Stripe retries for up to three days and `stripe listen` replays freely.

**Out-of-order delivery is normal and is guarded by `last_event_at`.** The upsert carries
`WHERE excluded.last_event_at >= subscriptions.last_event_at`, so a delayed `subscription.updated`
cannot resurrect a tier a later `subscription.deleted` removed.

**A genuine internal failure returns non-2xx.** Returning 200 on failure is how an entitlement
silently never lands: Stripe marks it delivered, never retries, and nothing records that the
customer is not on the tier they paid for.

---

## 6. The push contract

Built in exactly one place, `entitlementBody.ts`, because it used to be built in two — TypeScript
for the install-first order and a SQL `jsonb_build_object` for the pay-first one. They had drifted:
the SQL one rounded four Stripe statuses onto `cancelled` and carried no period end. **Which
behaviour a customer got depended on whether they paid or installed first.**

```jsonc
{
  "forge": "github", "account": "QuantaMinds",
  "tier": "team",              // "free" when the status is not a paying one
  "state": "active",           // see the table below
  "seats_included": 4,
  "payment_ref": "sub_…",
  "byok": false,
  "reason": "",                // "stripe status canceled" when not paying
  "valid_through": 1792309161, // the ITEM's period end
  "as_of": 1789691888          // the event's timestamp; the reviewer orders on it
}
```

| Stripe status | pushed state |
|---|---|
| `trialing`, `active`, `past_due`, `unpaid`, `paused` | the same word |
| `canceled` | `cancelled` (Stripe spells it with one l) |
| `incomplete`, `incomplete_expired` | `incomplete` |
| anything else | **passed through raw** |

**An unknown status is passed through on purpose.** `POST /entitlement` refuses a state it does not
know, so a status Stripe ships tomorrow becomes a VISIBLE failed push in the outbox and leaves the
existing entitlement untouched. Mapping it to `cancelled` would cut off a paying customer silently,
on the day Stripe shipped it, with a 200 recorded for it.

**`byok` is pushed and the reviewer currently drops it** — there is no column for it. That is a
known gap, and it matters for metering: a BYOK customer pays less precisely because they supply
their own key and must not be charged credits. It is a prerequisite of the credits work, not of
this one.

---

## 7. `POST /entitlement` — the reviewer's only billing surface

`src/quantamind/serve/web/entitlement_route.py`, routed by `serve/web/post_routes.py`.

| status | when |
|---|---|
| 503 | `QUANTAMIND_PROVISION_SECRET` unset — refuses rather than opening |
| 401 | bad or missing bearer (`hmac.compare_digest`) |
| 400 | no forge/account/tier/state/as_of, a non-integer `as_of`, or **a state this build does not know** |
| 200 | the row **as the store now holds it** |

**The reply is read back out of the store, never echoed from the request.** The store can
acknowledge a write that then vanishes (section 2). A handler that echoed what it was sent would
report that vanished write as stored, and the billing side would mark the push delivered. The
first test of this did not catch it — sabotaging `record()` to a no-op left it green, because the
assertion was reading the echo it was meant to distrust.

**A 200 is not enough on the billing side either.** `drainPushes` compares the echoed `tier`,
`state` and `seats_included` against what it sent; a 200 whose echo disagrees is NOT delivered and
the row stays pending with an attempt count.

---

It is the only billing route this service ANSWERS. Since seats and credits, this service also
ASKS billing one question per pull request — see "Seats and credits, asked on every pull request".

## 8. Running it end to end, locally

**Terminal 1 — the reviewer.** Needs `QUANTAMIND_PROVISION_SECRET` shared with the billing service:

```bash
uv run quantamind serve --port 7331
```

**Terminal 2 — the billing service**, with `REVIEWER_URL=http://localhost:7331`:

```bash
cd QuantaMind_Website/server && npx tsx src/index.ts
```

**Terminal 3 — the forwarder.** Its `whsec_` must match `STRIPE_WEBHOOK_SECRET`:

```bash
stripe listen --forward-to localhost:8787/billing/stripe/webhook \
  --events customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,checkout.session.completed
```

**Terminal 4 — make something happen:**

```bash
CUS=$(stripe customers create --email dev@quantamind.co --source tok_visa | jq -r .id)
stripe subscriptions create --customer "$CUS" \
  -d "items[0][price]=price_1UGfiCGY5MuBVWoyiOyqLh6G" -d "items[0][quantity]=4"
```

The subscription arrives before any forge account is known, so the outcome is `unlinked` and
nothing is pushed — that is correct, and the install link is what closes it. Mint one, then hit the
Setup URL the way GitHub would:

```bash
curl -i "http://127.0.0.1:8787/billing/forge/setup?installation_id=<real id>&state=<token>"
```

**Cancel it** — the CLI's `cancel` prompts, so go through the raw API:

```bash
stripe delete /v1/subscriptions/sub_… --confirm
```

`checkout.session.completed` cannot be driven by `stripe trigger` on this account: Managed Payments
rejects the `payment_intent_data.shipping` in Stripe's own fixture. `server/test/installLink.test.ts`
synthesises it instead, which is the reliable path anyway — it lets `client_reference_id` be present
or absent on demand, the single branch that separates the two onboarding orders.

---

## 9. What was verified against real Stripe, and what was not

**Verified against the sandbox on 2026-09-18**, not asserted from a hand-built payload:

- a real `customer.subscription.created` at 4 seats → `subscriptions` row with a real
  `current_period_end` (2026-10-18), pushed and stored as `github/QuantaMinds team active`
- the install link redeemed once, a second attempt refused, the entitlement drained and read back
  at `attempts=1, last_status=200`
- `paid_access.decide` returning `PAID` now, `STALE_RECORD` one second past the period, and
  `EXPIRED` eight days past it — the boundary that only exists because `valid_through` survived
- a real `customer.subscription.deleted` → `free (cancelled)` with `reason: stripe status canceled`
- an installation id resolved to its account against the live GitHub App API

**Not verified, and named rather than left to be discovered:**

- **No checkout has been completed through the hosted page.** That needs card entry in a browser.
  What is exercised is everything downstream of the payment succeeding.
- **`tests/live/` does not cover Stripe.** Adding a path that needs a Stripe key and outbound
  network would make `just verify` fail on any machine without one. Section 8 is a manual
  procedure, and this section is its record — which is weaker than a test and is not being
  presented as one.
- **Nothing validates that a price id names the $29 price.** It is configuration.
- **Out-of-order deliveries have never been observed in the wild**, only constructed. The guard is
  tested; the scenario is inferred from Stripe's own documentation saying order is not guaranteed.

---

## 10. What was removed, and why

Removed from this repository on 2026-09-18, in a single revertable commit:

| removed | what it did |
|---|---|
| `ingest/payments/stripe_api.py`, `checkout.py` | the outbound call, and Stripe's bracket-form encoder |
| `serve/webhook_stripe.py` | HMAC verification of Stripe's signature and timestamp |
| `serve/stripe_event.py` | reading `customer.subscription.*` into a `Subscription` |
| `serve/web/checkout_route.py`, `stripe_hook.py` | `POST /billing/checkout`, `POST /billing/webhook` |
| `store/billing/subscriptions.py`, `types/billing/` | the reviewer's own copy of Stripe's state |
| `types/deployment.Destination.PAYMENTS` | an outbound destination nothing reaches any more |
| `Settings.stripe_price_id`, `billing_success_url`, `billing_cancel_url` | configuration with no reader |

**Roughly 600 of those lines were reimplementations of things an SDK does** — form encoding, HMAC
verification, event parsing — written that way because `pyproject.toml` declares
`dependencies = []`. That constraint is right for this service and is the reason the work does not
belong here: on the billing side `stripe.webhooks.constructEvent` does all three, from Stripe's own
library, and every API-version bump is theirs to absorb rather than ours.

**What was kept, because it was better than what replaced it:** `verify/paid_access.py`. Its
verdicts — especially `STALE_RECORD` — are a distinction the entitlement store's five-value `State`
did not make, and it was ported to read `Coverage` rather than deleted with the rest.

**The `subscription` table was NOT dropped.** Dropping it is a destructive migration; the deployed
store cannot be inspected from a development machine; an empty table costs nothing and a lost row
cannot be recovered. It should be dropped once the Postgres ledger has run in production long
enough to be sure nothing is owed to those rows.

**The removed code is in git history, not gone.** The commit that deleted it names every file.

---

## 11. Before this touches the live account

1. **Archive `price_1U9FpWGwi83EhBSFIbuj2gSP`** ($39) or accept it as the real price and correct
   `docs/product/pricing.md`. They currently disagree and the page is published.
2. **Create the Team and Team-BYOK prices on the live account** and set `STRIPE_PRICE_TEAM` and
   `STRIPE_PRICE_TEAM_BYOK` to them.
3. **Register the webhook endpoint** in the live Dashboard against the deployed billing service,
   subscribed to the three `customer.subscription.*` events and `checkout.session.completed`, and
   set `STRIPE_WEBHOOK_SECRET` to the signing secret it issues. **This is not the `whsec_` that
   `stripe listen` prints** — that one is for local forwarding only.
4. **Rotate the sandbox `sk_test_` key.** It passed through a chat transcript during development.
5. **Set `QUANTAMIND_PROVISION_SECRET` to the same value on both services**, and rotate it
   independently of everything else — it is the only thing standing between a stranger and a free
   paid tier.
6. **Check the clock on both.** The reviewer compares `as_of`; Stripe rejects a signature more than
   300 seconds out.
7. **Apply migration `0013_seats_credits.sql`** on the billing database, and set on the billing
   service `STRIPE_PRICE_CREDIT` (the $1 one-time price) and `BYOK_ENCRYPTION_KEY` (32 random bytes,
   base64, from Secret Manager — losing it makes every saved customer key unreadable).
8. **Set `QUANTAMIND_BILLING_URL`** on the reviewer to the billing service. Unset, every pull request
   is decided from the cached plan: paying accounts reviewed unmetered, nobody charged.
9. **Schedule the drain.** `POST /billing/push/drain` every few minutes (Cloud Scheduler, same
   bearer). Nothing else retries a failed entitlement push.

---

## 12. Seats and credits, asked on every pull request

Before anything is cloned, the reviewer (`serve/review/admission.py`) asks
`POST /billing/review/authorize` with the author's GitHub **id**, the repository's visibility, and
whether it will call a model. The billing service (`server/src/billing/admission.ts`) answers in one
transaction with the account row locked, so two pull requests cannot both take the last seat or the
last credit:

| situation | answer |
|---|---|
| unpaid account, public repository | `free` — deterministic review, no model, no credit |
| unpaid account, private repository | `refused` — `private_needs_plan` |
| author is a bot (`user.type == "Bot"`) | `free` — never a seat, never a credit |
| paid, author holds a seat or one is free | `full` — seat assigned automatically, 1 credit reserved |
| paid, every seat taken | private: `refused` (`seat_full`, names the author); public: `free` + a footer naming them |
| paid, seated, no credits left | `refused` — `no_credits`, with the reset date |
| own-key plan | `full` with the customer's key, no credit; `byok_key_missing` if none is saved |

**One credit is one model review of one head commit**, keyed `forge:account:repo#pr@sha`, so a
redelivered webhook is charged once. Each paid seat brings 15 per billing period, pooled; bought
credits (`$1`, a one-time Checkout) never expire; the allowance is spent first.

**Every exit settles.** `serve/review/gate.py` calls `POST /billing/review/settle`: only a review
that reached someone and consulted a model keeps its credit. Nothing to say, a duplicate, a model
that never answered, or a crash are refunded — into the same bucket and period.

**When billing does not answer**, the reviewer decides from the cached plan with
`verify/paid_access.decide` (the same 7-day grace rule billing applies): a paying account is
reviewed in full and UNMETERED, logged as exactly that; anyone else gets only what is free.
Air-gapped refuses `Destination.BILLING` and always takes this path.

**Verified across both services on 2026-09-22**, with signed webhooks through the real listener:
seat 1 and 2 assigned, a third developer refused by name with nothing cloned, all 30 credits used
→ refused with the reset date, a Stripe-signed credit purchase applied once despite a replay and
spent next, and the billing service stopped → reviewed unmetered. That run found the
microsecond-precision bug described in `server/src/billing/admission.ts`'s balance query.

## 13. The customer's own model key

The billing service stores it encrypted (AES-256-GCM under `BYOK_ENCRYPTION_KEY`), validated with
Google before saving, readable only as its last four characters. It is returned in the authorize
reply for one review; the reviewer carries it as `GeminiKey` through every model call to
`infer/vertex.endpoint`, which sends it as an `x-goog-api-key` header to the Gemini API — never in
a URL, never on `Settings`, never logged. Without a key a BYOK review is refused rather than run on
our model.

