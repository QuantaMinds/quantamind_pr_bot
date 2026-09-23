# QuantaMind

### Write the rules once. We enforce them on every change — and prove the same answer twice.

**Pre-seed · $500K**

> **Eleven slides. The appendix is the data room, not slide twelve.**
>
> **This deck makes no claim about what a competitor lacks.** Six such claims were written here
> and all six turned out false — rivals ship rules, dashboards, merge blocking, permanent free
> tiers, and a fourth check outcome. They are listed at the end. **What is left i s what we can
> demonstrate**, which is a smaller deck and a claim that does not expire when someone else ships.

---

## 1 · The Problem

# AI writes code faster than people can check it.

Changes pile up, go in unread, and the bugs land in production.

| | |
|---|---|
| **32.7%** | of AI changes merge — humans: **84.5%** |
| **16 hrs** | before anyone picks one up — human work: **~200 min** |
| **+243%** | incidents per change *(reported — see appendix)* |

**Review isn't the slow part.** Once somebody starts, an AI change is read *faster* than a human
one — 194 min against 252. **All of the delay is in getting picked up.**

*Merge rates, pickup and review time: LinearB, 2026 Benchmarks — 8.1M pull requests, ~4,800 teams.
Incidents: Faros AI, 2026 — 22,000 developers, via secondary summary.*

---

## 2 · The Solution

# You write the rules once. A parser decides them, every change.

### Enforce the rules your team wrote
Break one and the change can't merge — **and the verdict is the same tomorrow.**

### Publish what we couldn't check
Which files we read, and which we did not. On every change.

**Prose can't be enforced**, so judgement calls are labelled and never block.
Today: Python, three rule kinds. **We don't claim to find more bugs than anyone else.**

**And we don't claim blocking reduces defects.** DORA measured approval gates against change fail
rate and found **no correlation**. What enforcement buys is that the rule is applied the same way
every time and can be proved afterwards — not a lower bug count. *(The full objection, and why
DORA's finding is about human approval boards rather than automation, is in the appendix.)*

---

## 3 · How It Works

# A developer sees only step 4.

| | | |
|---|---|---|
| **1** | **Check the rules** | Your rule file. No model. **Same commit, same verdict** |
| **2** | **Rank the files** | From this repository's own history |
| **3** | **Read the top** | The model reads only there |
| **4** | **Answer** | Blocked, or where to look |

**It also runs before the pull request exists** — `/qm-review` over uncommitted work, no network
call. *"Blocked" means a commit status that fails; turning that into a wall is your host's setting,
and GitHub reserves required checks for paid plans on private repos.*

---

## 4 · The Denominator

# The compliance number we report is one you can defend.

Four outcomes: `passed` · `broken` · **`couldn't tell`** · `a machine can't settle it`.
**Only the first two reach the rate.**

**A file nothing could parse never becomes a tick.** If it did, a repository could read as 100%
compliant with checks that never ran — and an auditor who finds one such row stops believing the
whole table.

**Conceded:** CodeRabbit ships an **Inconclusive** status for *"analysis that could not be
completed."* **Having a fourth outcome is not ours.** What we do with it is: `UNCHECKABLE` is
excluded from the denominator by construction, and every row is exportable with the commit that
lets you re-run it.

---

## 5 · Team

# We falsify our own claims. That is the method, and it is the product.

| | | |
|---|---|---|
| **Dhanush G** · CEO | Systems engineering | Test engines, agent pipelines |
| **Chirag V K** · CTO | Backend, infrastructure | DevOps, hardware testing |
| **KN Gowri** · CDO | Data science | Pipelines, test sets, validation |
| **Aanya Sampath** · COO | Operations | Go-to-market |

**Seven years together, since engineering school.**

**We pre-registered our first product idea, measured it, got a null — relative risk 1.040 against a
1.5 threshold — and killed it rather than defend it.** The claim we build on now is the one that
survived, and it reproduced on **six repositories we had never touched.**

**This month we disproved six of our own competitive claims and wrote them into this deck.** It is
the same instrument we point at a customer's code.

---

## 6 · Competition

# Blocking a merge is table stakes now. What decides it isn't.

| | CodeRabbit | Greptile | Qodo | **QuantaMind** |
|---|---|---|---|---|
| Deterministic rule engine | `ast-grep` | Opengrep | rules system | `.quantamind/rules.toml` |
| What decides the **blocking** verdict | rules **and model-judged checks** | rules **and model review** | **an agent** | **a parser, only** |
| Re-run proof published | — | — | — | **a 3-run digest, every build** |
| Per developer / month | $24–30, **PR authors only** | $30 + $1/review | ~$30 | **$29, every developer** |

**A model cannot be re-run to the same answer. A parser can — and we show it rather than assert it:**

> **Three runs over the same commit: 4,282 rows, one digest — `4ae0422b7a18`.**

**Rules, deterministic engines, dashboards, merge blocking and permanent free tiers all exist
elsewhere** — this deck claimed otherwise six times and was wrong six times. **What is left is that
nothing model-decided can reach our blocking verdict, and that we publish the proof.**

*Rows checked against vendor documentation, September 2026.*

---

## 7 · Business Model

# Per developer, per month.

| **Free** | **Team** | **Enterprise** |
|---|---|---|
| **$0** | **$29** | **from $60** |
| public repositories | per seat · 15 reviews a seat / month · $1 each after | per seat · metered |

**Inference is 4–7% of the price** — $1.20–$2.00 per developer per month against $29, measured on
68 billed requests. **The enforcement half runs no model at all.**

*We do not quote a gross margin here. The figure we used to print assumed a fair-use cap on model
reviews that **is not built** — the Ask names it. A margin resting on an unbuilt gate is a number we
cannot defend, so it is out until the gate is.*

**Break-even: 24 minutes per developer per month.** A senior engineer at $150K costs ~$72/hour —
salary only; fully loaded it's nearer 17 minutes. **We quote the harder number.** We price into
Semgrep at $35/contributor and SonarQube by lines of code, not the $24–30 AI-review band.

---

## 8 · Defensibility

# Three claims, and none of them is something a rival lacks.

**1 · A parser decides the block, and it re-runs.** Agent-decided verdicts can't. We measured the
cost: the same reviewer, same 173 defects, twice — **91, then 84.** A ±4-point swing from
nondeterminism alone. Ours is a digest you can watch reproduce.

**2 · The replay is model-free.** Six months of a prospect's history costs us CPU and costs a
model-per-change reviewer a full inference pass per historical change. **That's why we can hand it
to everyone.**

**3 · The method compounds, and no release note can falsify it.** Six competitive claims disproved
and published in one month. **A team that will not ship a number it cannot defend is what a
compliance buyer is actually purchasing.**

**Copyable in a quarter:** rules, blocking, dashboards, coverage lines, a free tier. **This category
ships those every month, and we don't sell them as a moat.**

---

## 9 · Go-to-Market

# Your own repository is the demo — and you run it yourself.

**Clone stays with you** → `quantamind retrospective` → **six months, replayed**

**No sign-up. No install of ours on your servers. Nothing leaves your machine.**

Their cost per prospect is a model call on every historical change. **Ours is CPU.**

> *We don't publish a benchmark — benchmarks are chosen by the vendor.*

---

## 10 · Market

# Only the bottom row is bottom-up. It's the one we're held to.

| | | |
|---|---|---|
| **SOM** | **$21M ARR** | **1,500 companies × ~40 developers × $348** |
| SAM | *not yet sized* | teams on GitHub with enough history to replay |
| TAM | $10.0B | 28.7M developers × $348 — population × price, and nothing more |

**28.7M is the most conservative count we found** (Evans Data); SlashData puts professionals at
36.5M and all developers at 47.2M. **$29 × 40 developers = $14K a year per company.**

---

## 11 · The Ask

# $500,000 · 18 months · four people

| | | |
|---|---|---|
| **1** | **Take payments** | Revenue in weeks, not quarters |
| **2** | **25 design partners** | Each replays their own history, free |
| **3** | **More languages, more rules** | Widens who can buy |
| **4** | **The audit report** | The artefact procurement pays for |

**Where we start from.** No customers, no revenue, no checkout. A product running end to end, and a
result that held on six repositories we'd never touched.

**What it has to prove.** That teams pay to have their own rules enforced. **Four open questions —
the cost model, an unbuilt tier gate, one deferred optimisation, and demand itself — are waiting on
the same event: the first customer.** That is what the $500K buys, and design partners are the
instrument, not a sales milestone.

---
---

# Appendix — the data room

*Confirmed = we read the primary source. Reported = a named secondary we did not confirm.*

| Claim | Source | Status |
|---|---|---|
| 42% AI-written; 96% don't fully trust; 48% verify; 38% more effort | Sonar, *State of Code*, 8 Jan 2026 — 1,100+ devs, self-reported | **Confirmed** |
| 32.7% vs 84.5% merge; 16+ hrs vs ~200 min pickup; 2.5× larger; 194 vs 252 min | LinearB, *2026 Benchmarks* — 8.1M PRs, ~4,800 teams, read on LinearB's page | **Confirmed** |
| +98% PRs merged, +91% review time, +154% size, +9% bugs | Faros AI, 2025 — 10,000+ devs, 1,255 teams. **Re-attributed: we had credited LinearB** | **Confirmed** |
| Incidents +243%; churn +861%; zero-review merges +31.3% | Faros AI, 2026 — 22,000 devs. PDF wouldn't parse; read from a secondary summary | **Reported** |
| Qodo's Rule System; org-level rules; "Merged Violations" metric | Qodo 2.1 announcement, 17 Feb 2026, and `docs.qodo.ai` — beta, GitHub only | **Confirmed** |
| Rivals block merges: CodeRabbit error mode, Qodo compliance gate | `docs.coderabbit.ai/pr-reviews/pre-merge-checks`; Qodo compliance docs | **Confirmed** |
| **CodeRabbit reports Inconclusive — "analysis that could not be completed"** | `docs.coderabbit.ai/pr-reviews/pre-merge-checks`, read 2026-09-11 | **Confirmed** |
| Greptile's analytics dashboard — and that it is *not* DORA or cycle time | greptile.com docs. A secondary source said otherwise and was wrong | **Confirmed** |
| Competitor pricing; `ast-grep` custom rules; CodeRabbit counts PR authors as seats | Vendor pricing pages, `docs.coderabbit.ai` | **Confirmed** |
| 28.7M professional developers | Evans Data; SlashData 36.5M / 47.2M. We use the lowest | **Confirmed** |
| Approval by an external body: negative on lead time, deployment frequency and restore time; **no correlation with change fail rate**; 2.6× more likely to be low performers | DORA, *Accelerate State of DevOps* 2019, and `dora.dev` "Streamlining change approval" | **Confirmed** |
| 35–91% of static analysis warnings are unactionable; alert fatigue is the documented consequence | Peer-reviewed static-analysis literature, incl. *Why Don't Software Developers Use Static Analysis Tools* (ICSE) | **Confirmed** |
| SOC 2 CC8.1 asks for programmatic enforcement, and samples branch protection config and CI logs | SOC 2 control guidance, read 2026-09-15 | **Confirmed** |
| ±4-point nondeterminism floor; 3-run digest; margin; routing result | Corpus noise-floor run; `assert_deterministic.py`; 68 billed requests; six unseen repos | **Ours** |

## The strongest objection to this product, and our answer

**DORA's research says change gates do not work, and a reader who knows it will raise it.** We would
rather hand it over.

> Formal change management requiring approval from an **external body** is negatively correlated
> with lead time, deployment frequency and restore time, and has **no correlation with change fail
> rate**. Respondents were **2.6× more likely to be low performers** — *"worse than having no change
> approval process at all."*

**Read literally, that is an argument against everything on slide two.** Three things about it
matter, in order:

**One — it is measuring a human bottleneck, not a gate.** The finding is about a board or a senior
manager who was not involved in the work. **DORA's own recommended alternative is ours:** *"change
approvals are best implemented through peer review during the development process, **supplemented by
automation to detect, prevent, and correct bad changes early**."* A parser that runs in the pipeline
and needs nobody's calendar is the thing they prescribe, not the thing they condemn.

**Two — the "no correlation with change fail rate" half is the one that constrains us, and we accept
it.** It is why this deck does not claim that blocking reduces defects. Enforcement buys
**consistency and provability**; it does not buy a lower bug count, and any pitch that says
otherwise is contradicting the best-known dataset in the field.

**Three — a gate is softer than "cannot merge" sounds, and we say so on slide three.** A repository
admin can bypass branch protection unless `enforce_admins` is set, approvals get rubber-stamped, and
GitHub reserves required checks for paid plans on private repositories. **What we actually promise is
a verdict that is recorded whether or not somebody overrides it** — and an override visible in the
record is the more useful artefact anyway, because *"was this ever bypassed?"* is a question only a
recorded gate can answer.

## Why enforcement rather than better detection

**Advisory does not degrade gracefully; it collapses.** The static-analysis literature puts
**35–91% of warnings** in the unactionable range, and the documented consequence is alert fatigue —
developers become desensitised and stop reading the channel, losing the fraction that was right along
with the rest. It is the same shape as the 36% noise finding on the market leader, and as our own
25%-correct measurement.

**And enforcement is what an auditor can accept.** SOC 2 **CC8.1** asks for evidence that only
approved changes reached production, and auditors sample **branch protection configuration, CI logs
and per-deployment proof that a check passed before the merge**. A bot comment is not evidence. A
recorded verdict is. That is the budget this is sold into.

## Six claims we made and disproved

**Every one was a claim about what a competitor lacked. All six were false.**

| We said | They ship |
|---|---|
| "Nobody enforces the standards you wrote" | Qodo Rule System (Feb 2026); CodeRabbit `ast-grep` |
| "You get back: comments" | All three ship analytics dashboards |
| "Their free tier is a trial" | CodeRabbit and Greptile are permanent and uncapped |
| "Everyone else leaves a comment; we stop the merge" | CodeRabbit error mode; Qodo's compliance gate |
| "A check that couldn't run has nowhere else to go" | **CodeRabbit's Inconclusive status** |
| "A parser decides it — theirs is a model" | **Greptile ships Opengrep pattern rules; CodeRabbit ships `ast-grep`** |

**The lesson, and the reason this deck reads differently from the last version:** you cannot
differentiate on absence in a category that ships a feature a month. **We now claim only what we can
demonstrate.**

## Other corrections during verification

A figure credited to LinearB is **Faros AI's**. "The pile tripled" was unsupported — the pile
doubled; incidents tripled. Two unsourced review-hours figures were cut. "Their reviews cost tokens,
ours cost CPU" was false — **the asymmetry is the replay, not the review.**

**A collision a diligence analyst will hit.** LinearB and a 2026 Faros write-up circulate identical
figures to one decimal place from different samples. Both can't be primary. **We cite LinearB,
which publishes its methodology.**

## What we are not better at

CodeRabbit writes your tests, answers questions, scans for vulnerabilities, holds **SOC 2 Type II**,
and has a bigger free tier. Greptile indexes your whole codebase. **We build none of that, and we
are not better than either at finding bugs.** Nobody in this market has shown they are — them or us.
