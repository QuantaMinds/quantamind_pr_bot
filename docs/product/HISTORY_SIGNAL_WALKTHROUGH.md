# QuantaMind — how it works, and a week in an engineer's life

> **Derived document.** Every measurement here is copied from `QUANTAMIND.md`, which is
> canonical. Reconciled against it on 2026-08-14. If the two disagree, that one wins and
> this is the bug.

**Rewritten 2026-08-13.** This replaces an earlier draft built on a design the measurements
falsified. The build plan is `docs/plans/delivered/gravity-reviewer-build-plan.md`; the evidence is in
`docs/findings/SIGNAL_SEARCH_LOG_2026-08.md` and
`docs/findings/HISTORY_SIGNAL_BACKTEST_2026-08.md`.

> **STALE BANNER CORRECTED 2026-09-11. THIS DOCUMENT SAID "NOTHING HERE IS SHIPPED" AND THAT IS
> FALSE.** Ten layers are built, the webhook reviews real pull requests, and `quantamind
> retrospective` runs against any clone. This is the same failure `what-to-say.md` records about
> itself: a document that is not re-derived does not decay into vagueness, it states the opposite
> of the truth in confident prose.
>
> **Two further things here are superseded and are kept only because the narrative rests on them.**
> The product ranks and allocates at **file** level, not function level — the function-level arm was
> measured and not shipped. And the model now runs on **every** reviewable change over the funded
> files; the tier table below describes a firing gate that no longer decides whether we speak.
> → `docs/product/HOW_IT_WORKS.md` is the current description.

Numbers inside the mock comments are labelled illustrative; every
number outside them is measured and cited.

---

## The product in one paragraph

Every AI reviewer reads the whole diff at the same depth. That is simultaneously why they cost
what they cost and why an independent audit found **36% of one incumbent's comments were noise
or nitpicking**. QuantaMind does the opposite: a free, model-free pass ranks the changed
functions by how often each has needed a follow-up fix, and that ranking decides where a model
is spent — deep on the one or two units history says changes come back to, nothing on the cold
ones. Structural claims the model makes are checked by the parser before publication. And on
every pull request it says plainly what it could not analyse. **Seven shipping reviewers were
checked in August 2026 and none could express it; that is a dated survey, not a property of the
category, and it is said as a capability of ours rather than a claim about everyone else.**

---

## The design, in the order it runs

```
pull request opens
  │
  ├─ 1. RANK        every changed function, globally, by prior-year touch count
  │                 (file-level ranking only where no function can be resolved)
  │
  ├─ 2. ALLOCATE    rank 1 → deep read.  rank 2-3 → shallow.  cold → no model call
  │
  ├─ 3. READ        the model, on those units only, returning structured findings
  │
  ├─ 4. VERIFY      parser checks every structural claim; contradicted claims are dropped
  │
  └─ 5. SAY         one comment, or silence — plus the coverage line, always
```

**Function-level ranking is currently UNPROVEN and the product ships on file-level ranking.**
An earlier comparison appeared to show functions beating files, and a nested file-then-function
strategy performing worst of all. **Both runs were void** — they read patch content from
blob-filtered clones, where `git log -p` exits non-zero mid-stream and the harness did not check
the return code, so each run silently analysed a different truncated slice of history.

What is measured and sound is **file-level ranking: 85.3% top-1 against a 72.0% null across
4,293 events in 17 of 17 repositories**, produced by a code path that reads no file contents.
The allocator is built on that. Whether function granularity does better — and therefore
whether "finer than what CodeScene and CodeRabbit ship" is a claim we own — is a rerun pending
on full-object clones, and is not asserted here until it lands.

---

## Which languages this works in

Priya's service is Python, but the signal is not. Measured at file level across six languages,
every one positive, with **Python in the middle rather than at the top**:

| Language | Events | Lift over its null ranker |
|---|---|---|
| TypeScript | 400 | **+26.0 points** |
| Java | 41 | +17.1 |
| Python | 5,242 | +14.5 |
| C++ | 63 | +14.3 |
| Go | 185 | +9.2 |
| JavaScript | 168 | +8.9 |

**What this does and does not license.** It shows the history signal exists in these languages.
It does **not** show that function-level extraction works in them — that needs a parser per
language and re-measurement, and the non-Python samples are small. Ship Python first because
that is where the instrument is; the addressable surface is not Python-shaped.

---

## Day 0 — install

One GitHub App. **Read-only on code, write-only on a comment.** No merge rights, no customer
model key, no code sent anywhere on the free tier.

It reads the repository's history once — roughly twenty minutes on a large repository — and
builds one index: for every function, how often changing it has required a follow-up, and which
functions those follow-ups touched.

---

## Day 0, twenty minutes later — the retrospective

**We do not ask anyone to wait a month to see whether this works.** A month of silence is how a
tool gets forgotten before it is judged, and it is unnecessary here: the counterfactual is
already in the repository. The same pipeline runs **backwards** over merged pull requests, and
the answer lands during the install.

```
QuantaMind — what we would have said, on your last 6 months     ← illustrative

  340 merged pull requests
   47 needed a follow-up fix within two weeks

  We would have commented on 31 pull requests — 9% of them.
  On 22 of the 47 that came back, we would have named the function
  the fix returned to.

  Your reviewer left an inline finding on 6 of the 47.
```

That is their repository, their number, before they have committed to anything. **A reviewer
that runs a model over every diff cannot open with this** — replaying 340 pull requests costs
them 340 pull requests of inference. Our deterministic pass costs compute.

**The one way this report can lie is lookahead**, and we have already been bitten by it: history
used for ranking must be bounded by each pull request's parent commit, never by date, or the
signal quietly knows the answer. The bound is asserted with `git merge-base --is-ancestor`, and
a sabotage run that deliberately leaks future commits must move the score. If it does not, the
report is void.

---

## Day 0 — live immediately, narrow on purpose

It starts commenting the same day. What ramps is **breadth, not time**.

| Tier | Fires when | Measured volume |
|---|---|---|
| **Start here** | top-ranked unit is in the repository's **top decile** of prior touch counts | **10–12%**, measured across eight repositories spanning an 80× velocity range |
| Widen once | top two ranked units | untested |

**A percentile, never a fixed number.** An absolute threshold does not transfer: "twelve prior
touches" fired on 11% of one repository and 53% of another. The percentile self-calibrates, and
that is what holds the comment volume steady across a repository doing 40 pull requests a
quarter and one doing 1,700.

**What this tier is not yet proven to do.** Measured precision at that volume ranges from 79%
on the best repository to 0% on two small ones, and on the largest sample the thing being
predicted — *a fix touches this unit again within a fortnight* — is nearly certain by activity
alone. See `docs/findings/RETROSPECTIVE_SWEEP_2026-08.md`: the ranking is sound, the **outcome
rule is the limiting instrument**, and no volume claim should be sold until it is tightened.

Widening is governed, not scheduled. Two signals, and **both must move the right way**:

| Signal | Required |
|---|---|
| Acceptance rate — findings a reviewer acted on | climbing |
| Post-merge defect rate, under our corrected attribution rule | flat or falling |

**One moving without the other is a red flag.** Acceptance rate alone can climb because the
tool got timid. A practitioner report puts first-pilot acceptance at 35–40%, rising past 60% as
context improves — a target to beat, and REPORTED, with no method we can check.

Both are measurable from the first week **because the tool is live**, which is the point: the
retrospective earns the install, the narrow tier earns the trust, and the paired gate decides
how far it opens.

---

## Tuesday, 10:40 — the pull request

Priya is the human on merge for the payments service. Ticket **PAY-3318**, *"Refund fails when
a partial capture exists."* A Cursor agent opens **PR #412**: four files, three functions
changed, thirty-four lines. The logic is right.

**CodeRabbit posts its walkthrough and no inline findings.** Normal, not a malfunction — in our
own draw, roughly three quarters of pull requests got a walkthrough with no inline finding.

QuantaMind ranks the three changed functions, spends its model budget on the top one, and
posts:

```
QuantaMind

Checked      4 files · 3 functions · 38 call sites resolved
Could not    dynamic dispatch in handlers/registry.py — 1 file unresolved
Found        1 finding

  process_refund()  ·  refunds/service.py
  Read closely: changed 9 times this year, the most of the 3 functions here.

  The partial-capture branch returns before the ledger entry is written.
  On a full refund the entry is written at line 88; on the new partial path
  the early return at line 71 skips it.

  Verified against the parsed control flow — both return paths confirmed.

  ← illustrative numbers
```

Three things about that comment are load-bearing:

- **The coverage line comes first**, and it names what was skipped and why. No competitor emits
  it.
- **The finding is semantic** — a missing write on a branch. A parser cannot find that; the
  model did, because the ranking told us to spend depth on that function.
- **"Verified against the parsed control flow"** is not decoration. If the model had claimed a
  branch the parser could not confirm, the claim would have been dropped and Priya would never
  have seen it.

## Tuesday, 10:52 — what Priya does

She opens `refunds/service.py`, reads lines 71 and 88, and sees it. Six lines to write the
ledger entry on the partial path. Pushed, merged at 11:04.

**Twelve minutes.** The counterfactual is a hotfix on Thursday and a refund discrepancy that
reaches a customer.

She does not think of it as a code review tool. She thinks of it as **the thing that knew which
function to look at**, which is the job the engineer who left the team used to do.

## Tuesday, 11:15 — the pull request where it says nothing

**PR #413** adds a webhook handler. New file, new functions, no history.

```
QuantaMind

Checked      2 files · 2 functions · 11 call sites resolved
Could not    nothing
Found        nothing
```

No inline comment, no badge, no "0 issues found" fanfare. **This is most pull requests, and it
is the design.** Research on function-level change prediction supports it directly: method-level
prediction beats coarser prediction **specifically when the acceptable number of
recommendations is small.** Firing rarely is the regime where the technique works.

## Tuesday, 14:02 — the pull request where it admits defeat

**PR #414** touches a module built on a handler registry.

```
QuantaMind

Checked      6 files · 2 of 9 functions
Could not    7 functions in dispatch/registry.py — handler table resolved at runtime.
             Ranking and analysis cover 2 of 9 changed functions here.
Found        nothing in what we could read

  This pull request is mostly outside what we can analyse. Treat the absence
  of findings as absence of analysis, not as a clean bill of health.
```

**This is the pillar no incumbent can copy.** Verified across seven shipping reviewers: not one
can report that it failed to analyse something. Cursor documents the collapse in its own words —
`neutral` means *"found issues, was cancelled, or hit an internal error"* — and states outright
that Bugbot emits no `skipped` conclusion. Publishing a blind spot contradicts a precision
claim, and their precision claim is their marketing.

## Friday — the tech lead's digest

One short email. No dashboard, nobody logs in.

```
Where this service reworks itself                    ← illustrative

  process_refund()    7 follow-up fixes in 9 changes
  apply_promotion()   5 in 8
  sync_ledger()       4 in 11

  These three account for 31% of the follow-up fixes in this service.
  They are where a human review is worth the most.
```

The index that drives the comments also says where to spend the human attention you have. Not
*"your code is bad"* — *"these three functions have cost you the most rework, and here are the
commits."*

## Quarterly — the conversation that renews the contract

The platform lead has to justify a seven-figure AI tooling line and cannot, because every
dashboard available attributes rework with a file-overlap rule that is **wrong on 67.9% of its
verdicts** — 36 of 53 verdicts share no symbol with the pull request they blame, reproduced at
36.1% and 35.7% survival on two further corpora.

They get one page: of the changes that needed a hotfix this quarter, what each reviewer said,
and what nobody caught.

**The tool being measured cannot be the tool that measures**, which is why the incumbent cannot
produce this page and we can.

---

## What Priya never sees

**Model findings that the parser contradicted.** If the model claims a caller that does not
exist, or a signature change that did not happen, the claim is dropped silently before
publication. A reviewer whose structural claims are checked before a human reads them is not
something anyone in this market offers.

This is also where the discipline has to be real: a verifier that never rejects anything is not
a verifier. **A sabotage test — inject a deliberately false structural claim, confirm it is
dropped — is a shipping requirement**, not a nice-to-have. That exact failure has already
happened twice in this repository's own tooling.

---

## What it costs

Free tier — ranking, structural checks, coverage line — costs us compute and nothing else. No
key, no seat, no credit; public repositories.

Paid tier, per pull request, at list prices:

| | Tokens | Cost |
|---|---|---|
| Deep call — prefix cache read | 20,000 at 0.1× | $0.010 |
| Deep call — ranked function and neighbours | 3,000 | $0.015 |
| Deep call — output including thinking | 2,000 | $0.050 |
| Two shallow calls — prefix cache read, once each | 2 × 20,000 at 0.1× | $0.020 |
| Two shallow calls — the function, low effort | 2 × 1,500 in | $0.015 |
| Two shallow calls — output | 2 × 600 out | $0.030 |
| **Per pull request, three calls** | | **≈ $0.140** |

Reading the whole diff at uniform depth costs roughly **$0.175**, so allocation saves **1.25×**
— not the 2× an earlier single-call version of this table implied. **Every request pays its own
cache read**, and the budget funds one deep call plus two shallow ones. At 200 pull requests a
month that is about **$28 of inference per repository**, and that figure is derived from a
specification rather than observed on real diffs.

---

## What is deliberately not in this product

- **"You forgot to change file X."** Tested: the co-change signal fired on genuine breakages but
  named the right file **0 times out of 8**. Withdrawn.
- **"This file is a hotspot, be careful."** Tested: RR 1.56, p = 0.334, firing on 36% of clean
  pull requests. Null.
- **Per-incident blame tickets.** Datadog already ships suspect commits on four documented
  criteria, plus ticket automation. We consume that webhook to measure our own defect rate; we
  do not rebuild it, and we do not name an author.
- **Any claim that unresolved code is riskier.** Falsified twice by our own measurements.

---

## What is still unproven, and would stop this

1. **Does a reviewer act on the routing line?** 75.0% top-1 against historical fixes is
   measured. Whether the hint helps a human *before* the bug exists is UNVERIFIED and is the
   whole commercial risk.
2. **Does allocation actually cut token cost** against uniform review? Asserted above,
   unmeasured.
3. **Does the productionised ranker reproduce the research ranker's numbers?** If not, the
   research is not the product.

All three are answered by the same month of shadow mode. None is answered by building more.
