"""Did this change do what it said, and does anything else depend on it.

WHAT: `explain(clone, sha, repo, number, paths, settings)` returns a `Summary`, or `None` when no
      model was consulted or the inputs could not be read.
WHY:  **THIS IS THE REVIEW'S ONE QUESTION, ASSEMBLED.** "Did what it said" needs the author's own
      description — a goal inferred from the diff makes the question circular, because a diff
      always achieves what the diff does. "Without disturbing anything else" needs the callers,
      which `parse/importers` finds by static import.

      **IT TAKES `paths`, NOT A `Reading`.** `allocate/` sits to the RIGHT of `infer/` and rule 7
      forbids reaching for it. The caller unpacks the allocation and passes the list, which is all
      this needs and keeps the layer direction intact.

      **`None` IS AN ABSENT SECTION, NOT A RESULT.** Unlike `deep_review.examine()`, where "found
      nothing" and "was unreachable" must stay distinguishable because a finding count is a claim,
      a missing summary simply means the comment renders without it and asserts nothing either way.
      The reason is printed so an operator can see which it was.
IMPORTS: ingest.diff, infer.change_summary, parse.importers, types.settings. Leftward only.
CONSUMED BY: `serve/review_delivery.py`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from quantamind.infer.change_summary import Summary, summarise
from quantamind.infer.vertex import InferenceFailed, Unavailable
from quantamind.ingest.diff import DiffReadFailed, stated_goal, unified_diff
from quantamind.ingest.standards.conventions import written
from quantamind.parse.importers import importers
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.settings import Settings


def _plainly(exc: Exception) -> str:
    """Why the review could not run, in words a developer can act on rather than a class name."""
    text = str(exc)
    if "MAX_TOKENS" in text:
        return "the change was too large to read in one pass."
    if "no access token" in text:
        return "the reviewer has no credentials configured."
    return f"the reviewer could not run: {text[:120]}"


def explain(
    clone: Path,
    head_sha: str,
    repo: str,
    number: int,
    paths: Sequence[str],
    settings: Settings,
    history: Mapping[str, int] | None = None,
    route: ModelRoute | None = None,
) -> tuple[Summary | None, str]:
    """What the change does, whether it did what the author said, and who it affects.

    **THE TWO HALVES OF THE REVIEW'S ONE QUESTION.** "Did what it said" needs the author's own
    description, because a goal inferred from the diff makes the question circular. "Without
    disturbing anything else" needs the callers, which `parse/importers` finds by static import.

    **`None` IS NOT-ASKED, AND AN OUTAGE IS ALSO `None` HERE.** Unlike `examine()`, which must
    distinguish "the model found nothing" from "the model was unreachable" because a finding count
    is a result, an absent summary is simply an absent section: the comment renders without it and
    claims nothing either way. The reason is printed for the operator.
    """
    if not settings.runs_model or not paths:
        return None, ""
    try:
        stated = stated_goal(repo, number)
        diff = unified_diff(repo, number)
        callers: list[str] = []
        for path in paths:
            found, _ = importers(clone, head_sha, path)
            callers.extend(found)
        told = summarise(
            diff,
            stated,
            project=settings.inference_project,
            importers=sorted(set(callers)),
            history=history,
            conventions=written(clone, head_sha),
            gcloud=settings.gcloud_path,
            route=route,
            model=settings.model,
        )
    except (InferenceFailed, Unavailable, DiffReadFailed) as exc:
        # **THE REASON IS RETURNED, NOT ONLY LOGGED.** A delivery hit MAX_TOKENS, the summary was
        # dropped, and the comment degraded into a file list with no verdict — indistinguishable
        # from a clean review to the developer reading it. The caller renders this as a refusal.
        print(f"[deliver] no summary: {type(exc).__name__}: {exc}", flush=True)
        return None, _plainly(exc)
    # **THE DEPENDENTS ARE ATTACHED HERE, NOT ASKED OF THE MODEL.** They came from a parser and
    # anyone can re-run them; the prose came from a model and carries its error rate.
    return replace(told, dependents=tuple(sorted(set(callers)))), ""
