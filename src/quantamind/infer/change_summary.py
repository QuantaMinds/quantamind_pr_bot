"""What this change does, in the author's terms, and whether it did what it said.

WHAT: `summarise(diff, stated, project)` returns a `Summary`: the change in plain words, whether it
      achieves the goal the author stated, and the reasoning. `Unavailable` when there are no
      credentials; a `Summary` with `consulted=False` is never fabricated here — the caller decides.
WHY:  **THE REVIEW'S ONE QUESTION IS WHETHER THE CHANGE DID WHAT IT SAID WITHOUT DISTURBING
      ANYTHING ELSE**, and neither half can be answered from the diff alone. "What it said" comes
      from the author's own title and body; a goal inferred from the code makes the question
      circular, because a diff always achieves what the diff does.

      **THIS IS A DIFFERENT TASK FROM FINDING DEFECTS, AND THE EVIDENCE AGAINST US IS ABOUT THE
      OTHER ONE.** Four blind pools put raw findings 66.7-82.1% wrong; that measured a model
      asserting a bug exists in code a human then had to check. Summarising a diff and comparing it
      to a paragraph the author wrote is a reading-comprehension task with both halves present in
      the prompt. It may well be reliable where finding defects was not — **and it is not yet
      measured, so nothing here may be stated as though it were.**

      **`achieves_goal` IS THREE-VALUED FOR THAT REASON.** True, False, and `None` for "the author
      stated no goal to check against" — an empty description is a real answer, and inventing a
      goal to grade against would manufacture agreement. A reviewer reading "achieves its goal"
      must be able to trust that a goal existed.
IMPORTS: stdlib, `ingest.diff` for `Stated`, and `infer.gemini` for the transport it already owns.
CONSUMED BY: `serve/deep_review.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from quantamind.infer import vertex
from quantamind.infer.diff_cap import capped
from quantamind.infer.summary_prompt import PROMPT
from quantamind.ingest.diff import Stated
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.spend import Spend, measured

# **CUT FROM 60,000 WHEN A REAL 27-FILE DELIVERY HIT MAX_TOKENS.** The diff shares the prompt
# with the conventions and the fact blocks, and a review that fails is worth less than a review
# of a truncated diff — but only because the truncation is MARKED, which is what `_capped` does.
# This comment previously asserted the cut was "visible in the output" and nothing made it so:
# the diff was sliced and handed over, and the model read a change that stopped mid-hunk with
# no way to know it had. Rule 14 — a comment may explain why, never assert whether.
MAX_DIFF_CHARS = 30_000


@dataclass(frozen=True, slots=True)
class Summary:
    """A plain-words account of the change, and whether it matches what was promised."""

    what_changed: str
    achieves_goal: bool | None
    reasoning: str
    impact: str = ""
    """One sentence on the callers. Empty when the model was not given an importer list."""

    breaks: bool | None = None
    """Whether this change breaks an existing caller. **THREE-VALUED, AND `None` IS THE DEFAULT.**

    "It will not break anything" is the most expensive sentence this product can print, because it
    is the one a reviewer acts on by not looking. `None` means the decisive information was not in
    front of the model — an empty importer list, a language we do not parse, a runtime behaviour a
    diff does not show — and it must render as "cannot tell", never as reassurance.
    """

    breaks_why: str = ""

    convention: str = ""

    spend: Spend = field(default_factory=Spend)
    """What producing this summary cost. Added to the deep pass by the caller."""
    """A rule from the team's own documents that this change contradicts. Empty when none is.

    **CONTEXT, NOT ENFORCEMENT.** Prose cannot be re-run on a commit and shown to give the same
    verdict, so this never becomes a `Checked` row and never enters the audit trail — that stays
    the parser's territory. What it can do is point a reader at a sentence they wrote themselves.
    """

    goal: str = ""
    """**THE PR DESCRIPTION, VERBATIM. A FACT, NOT A READING.**

    The goal is not something to infer or paraphrase: the author wrote it down, and it is the
    thing the change is measured against. Letting a model restate it would put a second author
    between the reviewer and what was actually promised, and a summary of a promise is where the
    promise quietly changes. It is quoted, and `achieves_goal` is judged against the quote.
    """

    dependents: tuple[str, ...] = ()
    """Files that statically import the changed code. **MEASURED, NOT SAID BY THE MODEL.**

    The prose fields above are a model's reading and carry its error rate. This is the output of
    `parse/importers`, which a parser produced and anyone can re-run on the same commit. They sit
    on one record because they describe one change, and they are rendered differently on purpose:
    a count of dependents is a fact, and a sentence about impact is a claim.
    """

    def __post_init__(self) -> None:
        if not self.what_changed.strip():
            raise ValueError("a summary with nothing in it is not a summary; raise instead")


def summarise(
    diff: str,
    stated: Stated,
    *,
    project: str,
    importers: Sequence[str] = (),
    history: Mapping[str, int] | None = None,
    conventions: Sequence[tuple[str, str]] = (),
    gcloud: str = "gcloud",
    location: str = "us-central1",
    route: ModelRoute | None = None,
    model: str = vertex.MODEL,
) -> Summary:
    """Ask the model what changed and whether it matches the author's stated purpose."""
    if not diff.strip():
        raise vertex.InferenceFailed("no diff to summarise")
    url, auth = vertex.endpoint(
        route, project=project, location=location, model=model, gcloud=gcloud
    )
    goal = stated.text() or "(the author wrote no description)"
    # **AN EMPTY LIST IS SAID IN WORDS, NOT LEFT AS A BLANK.** A blank section reads to a
    # model as "no information", and it would fill the gap; the sentence makes the absence
    # itself the fact, which is what `parse/importers` can actually support.
    touched = "\n".join(f"- {name}" for name in sorted(history or {})) or "- (none recorded)"
    imports = "\n".join(f"- {name}" for name in importers) or (
        "(no static Python import of these files was found anywhere in the repository)"
    )
    told_us = "\n\n".join(f"--- {name} ---\n{text}" for name, text in conventions) or (
        "(this repository keeps no convention document we recognise)"
    )
    past = "\n".join(f"- {p}: {n} prior fix(es)" for p, n in sorted((history or {}).items())) or (
        "(no fix history for these files in this repository)"
    )
    answer = vertex.post(
        url,
        auth,
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": PROMPT.format(
                                goal=goal,
                                diff=capped(diff, MAX_DIFF_CHARS),
                                files=touched,
                                importers=imports,
                                history=past,
                                conventions=told_us,
                            )
                        }
                    ],
                }
            ],
            # **RAISED FROM 2048 WHEN CONVENTIONS ENTERED THE PROMPT.** The reply is six short
            # fields, but the model's own reasoning counts against this budget, and a larger
            # input buys longer thinking. It failed as MAX_TOKENS rather than returning half a
            # review, which is `gemini._post`'s existing refusal working as designed.
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
        },
    )
    candidates = answer.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise vertex.InferenceFailed(f"no candidates in reply: {str(answer)[:160]}")
    first = candidates[0]
    if first.get("finishReason") != "STOP":
        raise vertex.InferenceFailed(f"finishReason {first.get('finishReason')!r}, not STOP")
    elapsed = answer.get("_ms", 0)
    text = str(first.get("content", {}).get("parts", [{}])[0].get("text", "")).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise vertex.InferenceFailed(f"reply was not JSON: {text[:160]}") from None
    achieved = payload.get("achieves_goal")
    return Summary(
        what_changed=str(payload.get("what_changed", "")).strip(),
        achieves_goal=achieved if isinstance(achieved, bool) else None,
        reasoning=str(payload.get("reasoning", "")).strip(),
        goal=stated.text(),
        impact=str(payload.get("impact", "")).strip(),
        breaks=payload.get("breaks") if isinstance(payload.get("breaks"), bool) else None,
        breaks_why=str(payload.get("breaks_why", "")).strip(),
        convention=str(payload.get("convention", "")).strip(),
        spend=measured(answer, elapsed if isinstance(elapsed, int) else 0),
    )
