# Pricing: what the whole product costs to run, and what to charge for it

**Written 2026-08-31.** Costs are measured on this repository's own instrumentation. Volume and
competitor prices are researched and cited. Every number that is assumed rather than measured says
so — `G3` exists because every pricing conversation before it was arithmetic over a figure nobody
had measured.

## What is actually being sold

Thirty of fifty plan rows are built, and they are not one product. They are three surfaces with
very different evidence behind them, and pricing them as a single AI-code-review seat undersells
two of them.

| surface | what it is | evidence | marginal cost |
|---|---|---|---|
| **The ranker** | decides which changed files are read hard, from fix history | **replicated out-of-sample**: 1.21% missed vs 3.12% alphabetical, six unseen repositories, n=2,400, p<1e-6 | none |
| **The standards engine** | rules as code (`D1a`), deterministic checks (`D1b`), a **blocking status check** (`D1f`), an append-only audit trail (`D4b`), per-repository compliance (`D5`) | reproducible by construction — a parser's verdict re-runs on the same commit | none |
| **Written standards as reviewer context** (`D1g`) | the team's `AGENTS.md` / `CONTRIBUTING.md` / `.cursorrules` read and given to the reviewer | **none — and this row is the correction.** An earlier version of the table above listed these as "read and **enforced**". They are not. `ingest/standards/conventions.py` says it plainly: *"THIS IS CONTEXT, NOT ENFORCEMENT… nothing read here becomes a `Checked` row or enters the audit trail."* Prose cannot be re-run on a commit and shown to give the same verdict, so it feeds `infer/` and inherits the reviewer's 25.0% | included in the review |
| **The model reviewer** | findings on the lines they concern | **25.0% correct**, 6 of 24, 95% CI 12.0–44.9%; the gate shows no measurable improvement | $0.065+/review |

**Two of the three cost nothing per review and carry the stronger evidence.** That is the pricing
thesis of this document.

**AND THE ENFORCEABLE SURFACE IS NARROWER THAN "THE STANDARDS ENGINE" SOUNDS.** What a parser can
decide today is three rule kinds — `forbid_call`, `forbid_import`, `naming_pattern` — declared in
`.quantamind/rules.toml`, **on Python files only**: `verify/rule_check.py` returns `UNCHECKABLE`
with `LANGUAGE_UNSUPPORTED` for anything else, which is correct and is not coverage. A fourth kind,
`MODEL_JUDGED`, is recorded `DEFERRED` and never blocks. **Nothing here is sold on prose the
customer has already written**, and any pricing argument that assumes otherwise is pricing a
capability that does not exist yet.

**~~THERE IS ALSO NO EXPORT.~~ BUILT 2026-08-31** — `quantamind compliance --repo owner/name
--export PATH` writes the whole trail as JSON with its own limits inside it. This paragraph named
the gap for a fortnight while D4b stayed ticked "exportable"; it is kept rather than deleted
because a document that quietly stops naming a gap it was right about teaches nobody anything. What
follows was true when written:** `D4b` records every check as it happens and nothing is backfilled;
reading it is `quantamind compliance --repo owner/name`. There is no file, no download, and no
scheduled export anywhere in the build plan. A compliance buyer asks for the artefact, not the
query.

## What one model review costs

Measured over 35 changes of `pallets/flask`: **1,181 input and 6,321 output tokens**, one call, 60
seconds. → `docs/findings/A6_WHAT_A_REVIEW_PRODUCES_2026-08.md`. The product calls
`gemini-2.5-pro` (`infer/vertex.py:MODEL`) at **$1.25 / $10.00** per million tokens.

| model | $/review | 15 PR/dev/mo | 20 |
|---|---|---|---|
| **gemini-2.5-pro — ships today** | **$0.0647** | $0.97 | $1.29 |
| gemini-3.1-pro | $0.0782 | $1.17 | $1.56 |
| gemini-3.6-flash | $0.0492 | $0.74 | $0.98 |
| gemini-2.5-flash | $0.0162 | $0.24 | $0.32 |

**Output is 97.7% of the bill**, and A6 records that most of it is the model's own reasoning rather
than its answer. Shortening reasoning is worth roughly forty times shortening the prompt.

**This is a FLOOR, for two reasons.** `serve/settle.py` calls `infer/prompt_once`, which does not
report usage — the reason `Spend.complete` exists — adding an uncounted 0.7–1.4 calls per review.
And flask changes are small; a monorepo diff could be 10–50× the input, though input is only 2% of
the bill. **Plan on $0.08–$0.10 per model review.**

At **12–20 pull requests per developer per month** (8.1M+ PRs, 4,800+ organisations), model COGS is
**$1.20–$2.00 per developer per month**. Infrastructure is ~$0.05. Nothing else is material.

## Which market this sits in

| product | price | what it sells |
|---|---|---|
| Snyk Team | $25/dev | security scanning |
| CodeRabbit Pro | $24/dev annual | AI review |
| Greptile Pro | $30/seat + **$1 per review** | AI review |
| Semgrep Team | **$35**/contributor, free ≤10 ($30 per module) | **custom rules, policy enforcement** |
| SonarQube Cloud | **by lines of code**, free ≤50K LOC | **quality gates, standards** |
| Semgrep full stack | $75/user | rules + supply chain + secrets |

**The standards market pays more than the AI-review market**, and the standards half is the half
with reproducible verdicts. Anchoring on CodeRabbit's $24 would price the strong half at the weak
half's rate. Greptile's **$1 per marginal review against our $0.065 cost** shows what the market
already tolerates.

## The tiers

| | **Free** | **Team — $29/dev/mo** | **Enterprise — from $60/dev/mo** |
|---|---|---|---|
| ranker, declared rules, team's own standards | yes | yes | yes |
| blocking status check `D1f` | yes | yes | yes |
| compliance table `D5`, audit trail `D4b` | 30 days | full history | full history |
| local + pre-PR review `E1`–`E3` | yes | yes | yes |
| web dashboard, cost view | yes | yes | yes |
| model reviewer | — | 15 reviews per seat / month, $1 each after | metered |
| cross-repo standards `D1e` | — | — | yes |
| SSO, self-host, residency, DPA, SLA | — | — | yes |
| **COGS at the cap** | **UNDECIDED — see below** | **$3.20–4.00** | metered |
| **gross margin** | n/a | **86% at cap, ~94% typical** | negotiated |
| seats | public repositories, no seat | per seat, assigned on first pull request | per seat |

**BUILT 2026-09-22 — THE GATE THE CORRECTION BELOW SAYS WAS MISSING NOW EXISTS.**
`serve/review/gate.py` decides every pull request before anything is cloned: an unpaid account gets
the model-free review on a public repository and nothing on a private one, and a paid one spends a
credit per reviewed commit (`serve/review/admission.py`, and the billing service's
`admission.ts`). So "free is model-free" is now enforced rather than intended, and the model cost
is metered per review rather than capped by fair use. **The correction below is left as written**:
it was true for the eleven days it stood, and a correction log that is edited to match what
happened later stops being evidence.

**CORRECTED 2026-09-11 — "FREE IS MODEL-FREE" IS A DESIGN, NOT A BUILT GATE, AND THE TABLE ABOVE
PRICED IT AS BUILT.** `serve/review/review_delivery.py` calls `examine()` on every reviewable
change; the only conditions are `settings.runs_model` (global) and a non-empty allocation, and
`allocate.plan()` always funds something. Entitlement is binary — `installations.entitled` gives
`may_review`, not a tier. **So there is no code path that makes Free model-free**, and its COGS is
$0 only if the gate gets built.

**Two options, and this document must not pick one silently.** Build the tier gate, and the Free
row and every argument resting on it stand as written. Or accept model COGS on Free — **$1.20–$2.00
per developer per month at 12–20 changes**, which at ten contributors is $12–$20 per free
repository per month, and then Free needs a cap and the "structurally free" argument is retired.
**Until it is decided, nothing may be pitched on Free costing us nothing.**

What survives either way: Free to ten contributors mirrors Semgrep, whose buyers are the buyers we
want, and **the retrospective replay is genuinely model-free** — `serve/retrospective.py` imports
`ingest`, `rank` and `store` and never `infer`.

**Team at $29 sits with Semgrep and SonarQube, not with CodeRabbit.** We are not selling better
findings — at 25% correct we would lose that argument, and `commercial-surface.md` already forbids
selling findings as a paid capability. We are selling **enforced standards with a trail that says
what was not checked**. The fair-use cap of 40 model reviews per developer per month is 2–3× the
benchmark, so almost nobody meets it, and it bounds the worst case at $4.00 against $29.

**Enterprise is a different buyer, not a bigger quota.** It sells procurement: SSO, residency,
self-hosting, a DPA, an SLA, and `D1e` — one standard defined once and enforced across every
repository, which is the only feature here that a platform team cannot get from a per-repo tool.

## BYOK is worth about 10%, and giving away more is a mistake

**Inference is 4–7% of the Team price.** A customer with their own key saves us $1.20–$2.00 per
developer per month. Halving the seat to "pass on the model cost" gives away $14.50 to save $2.00
and takes the tier from ~94% margin to ~50%.

**Price BYOK at $26/dev/mo — 10% off, slightly more than it saves us** — and sell it on what it is
for: their own rate card and committed spend, their residency and retention terms, and a model
choice they control. Those are procurement unlocks, and an enterprise buyer values them well above
the discount.

**BYOK must not become the cheap door to the same product.** An uncertified model makes every
correctness figure we publish untrue for that customer, so: allowlisted models at Team+, arbitrary
models at Enterprise only. `commercial-surface.md` already reaches this conclusion and it survives
the new numbers.

## What has to be true before quoting any of this

- **`prompt_once` must report usage.** Until then every cost here is a floor and every margin is
  optimistic by an unknown amount. It is the highest-value measurement outstanding.
- **A repository unlike flask.** All token figures come from one small codebase.
- **Reviews per repository per month is unmeasured.** The per-developer figure is borrowed from an
  industry benchmark, not from our installations — and seven tenant stores on a running container
  could answer it directly.
- **AI-assisted workflows have raised PR volume 30–40% without matching value.** Volume pricing
  captures that inflation on both sides: their bill and our cost.
- **If correctness leaves 25%, retier completely.** The model half would become the thing worth
  paying for, and the free tier would stop being able to include everything that works.
