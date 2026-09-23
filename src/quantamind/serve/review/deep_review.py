"""The reviewer pass: read the ranked files with a model, then keep only what a parser can anchor.

WHAT: `examine(...)` applies the allocation and settings, then `deep(...)` runs the model — ours
      or the customer's key — over the ranked files' diff and `verify/anchor.locate()` over every
      finding. Reports what survived and what was dropped, and by which mechanism.
WHY:  **THIS IS THE HALF THE EVIDENCE SAYS IS BAD, AND THE COUNTS ARE PRINTED FOR THAT REASON.**
      Raw findings measure 66.7-82.1% wrong across four blind rater pools at 0.013-0.037 correct
      findings per pull request. Nothing here makes that untrue. What this file does is ensure the
      only findings that reach a caller are ones whose quoted code is provably in the diff, and that
      the number discarded is a value rather than an absence.

      **THE PARSER RUNS AND THE MODEL JUDGE DOES NOT, DELIBERATELY.** A string comparison decides
      whether a snippet occurs in a diff, and it has no blind spots to share with the reviewer. Two
      same-family model judges were measured on 2026-08-20: one discarded 21% of a pool at F1 37.3%,
      the other 30% at F1 34.4% while losing 16 true findings of 100. **Neither is wired in, and a
      judge is not added until one clears its pre-registered bars on a corpus it was not built on.**

      **THE MODEL IS SHOWN ONLY THE RANKED FILES.** That is the thesis and it is also the bill.
IMPORTS: infer.gemini, verify.{anchor,publishable}, types.deep, and the prompt material from
      `serve/review/deep_prompt.py`. Rightmost layer, so all of them are allowed here -- and
      `verify/` still cannot see `infer/`, which is the property rule 7 protects.

      **THE RECORD, THE PRINTING AND THE PROMPT MATERIAL LEFT THIS FILE** (`types/deep.py`,
      `render/deep_report.py`, `serve/review/deep_prompt.py`) so what remains is one concern --
      running the pass -- which is rule 6.
CONSUMED BY: `serve/cli.py` behind `--deep`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from quantamind.allocate.depth import Reading
from quantamind.infer import gemini, vertex
from quantamind.infer.vertex import InferenceFailed, Unavailable
from quantamind.serve.review.deep_prompt import context_for, diff_for
from quantamind.serve.settle import settle
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.deep import Deep
from quantamind.types.settings import Settings
from quantamind.verify import publishable
from quantamind.verify.anchor import locate


def deep(
    clone: Path,
    sha: str,
    ranked: list[str],
    *,
    project: str,
    changed: list[str] | None = None,
    gcloud: str = "gcloud",
    route: ModelRoute | None = None,
    model: str = vertex.MODEL,
) -> Deep:
    """Read `ranked` with the model, keep only findings a parser can place in the diff.

    **THE MODEL READS ONLY `ranked`, BUT IS TOLD THE SHAPE OF THE WHOLE CHANGE.** Those are
    different scopes on purpose: the thesis is that inference goes only where the ranker pointed,
    while "6 files where your median is 2" is a fact about the change and would be false if
    counted over the three files we happened to fund.
    """
    text = diff_for(clone, sha, ranked)
    if not text.strip():
        # Not "the model found nothing" -- it was never asked, because those paths carry no diff.
        return Deep((), 0, 0, 0, 0, 0, tuple(ranked), consulted=False)
    found, spent = gemini.read(
        text,
        ranked,
        project=project,
        context=context_for(clone, sha, changed or ranked),
        gcloud=gcloud,
        route=route,
        model=model,
    )
    located = [f for f in (locate(x, text) for x in found) if f is not None]

    # **ANCHOR, THEN ORACLE, THEN THE MODEL'S OWN SECOND LOOK.** Ordered by cost: anchoring is
    # local and free, an oracle is one network call, and settling is two model calls. A finding
    # whose quote is not in the diff never reaches GitHub.
    # **COUNTED APART.** One counter for both read as "the oracles refuted one" when nothing had
    # been refuted and a claim was merely unaskable. → `types/deep.py:unresolvable`
    surviving, refuted, unresolvable = [], 0, 0
    for finding in located:
        ruling = publishable.gate(finding, text)
        if ruling.publishes:
            surviving.append(finding)
        elif ruling.unresolvable:
            unresolvable += 1
        else:
            refuted += 1

    kept, withdrawn = [], 0
    for finding in surviving:
        try:
            decided = settle(
                finding,
                project=project,
                today=date.today().isoformat(),
                route=route,
                model=model,
            )
        except (InferenceFailed, Unavailable):
            # **A SETTLE THAT COULD NOT RUN KEEPS THE FINDING.** Dropping on failure would make an
            # outage look like a filter working, which is the shape this project keeps catching.
            kept.append(finding)
            continue
        if decided.publishes:
            kept.append(finding)
        else:
            withdrawn += 1

    return Deep(
        tuple(kept),
        len(found),
        len(found) - len(located),
        refuted,
        unresolvable,
        withdrawn,
        tuple(ranked),
        # **A FLOOR WHEN ANYTHING WAS SETTLED.** `settle()` asks the model per surviving finding
        # through `infer/prompt_once`, which reports no usage — so this is a floor, and says so.
        spend=spent if not surviving else replace(spent, complete=False),
    )


def examine(
    clone: Path,
    head_sha: str,
    reading: Reading,
    changed: list[str],
    settings: Settings,
    route: ModelRoute | None = None,
) -> Deep | None:
    """Run the model over what the allocation funded, or say plainly it was never asked.

    **`None` IS NOT-CONSULTED, NOT A FINDING OF NOTHING**, and `runs_model` needs two deliberate
    acts, so no delivery costs money by default. **An outage returns `consulted=False`**, because a
    model that could not be reached must not read like one that read the diff and approved it.
    """
    if not settings.runs_model or not reading.paths:
        return None
    try:
        looked = deep(
            clone,
            head_sha,
            list(reading.paths),
            project=settings.inference_project,
            changed=changed,
            gcloud=settings.gcloud_path,
            route=route,
            model=settings.model,
        )
        # **PRINTED WHERE THE NUMBERS ARE PRODUCED.** These five counts were logged by
        # `serve/review_delivery.py`, which had to be handed every one of them to say a sentence
        # about work it did not do. Moving the line here means the depth, the raw count and the
        # three rejection counts have one reader, and a sixth count cannot be added without the
        # line that reports it being right there.
        print(f"[deliver] {reading.depth.value}: {reading.why}", flush=True)
        print(
            f"[deliver] model: {len(looked.anchored)} finding(s) kept of {looked.raw} raw "
            f"({looked.unanchored} unanchored, {looked.refuted} refuted, "
            f"{looked.withdrawn} withdrawn), consulted={looked.consulted}",
            flush=True,
        )
        return looked
    except (InferenceFailed, Unavailable) as exc:
        print(f"[deliver] the model was unreachable, ranking still stands: {exc}", flush=True)
        return Deep((), 0, 0, 0, 0, 0, tuple(reading.paths), consulted=False)
