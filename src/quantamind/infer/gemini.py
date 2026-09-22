"""Ask a model for defects in the files the ranker chose, and never for a line number.

WHAT: `read(diff, paths, key)` sends the diff restricted to `paths` and returns `Finding`s carrying
      a quote rather than a line. `Unavailable` when no credentials are configured.
WHY:  **THE MODEL IS ONLY EVER SHOWN WHAT THE RANKER SELECTED.** That is the product thesis in one
      line — decide where to look, then read hard only there — and it is also what bounds the bill.

      **IT IS NEVER ASKED FOR A LINE NUMBER, AND THAT IS THE ONE THING IN NINE DESIGNS THAT
      WORKED.** Five designs asked for a line and repaired it; all five failed, with 87.3% of claims
      quoting code absent from the line they cited. Design thirteen removed the field: the model
      quotes code, and the line is derived from where that quote sits, so the prose and the anchor
      cannot disagree because one is a function of the other. **Real-finding anchor failures went to
      ZERO of 86.**

      **STDLIB ONLY, BECAUSE `pyproject.toml` DECLARES `dependencies = []`.** The endpoint was
      written on `http.server` to hold that line and this holds it too — `urllib` and a token from
      `ingest/google_auth` (the metadata server, or `gcloud` on a laptop). A vendor SDK here
      would be the first runtime dependency this product takes.

      **NOTHING HERE IS PUBLISHED.** These findings are 66.7-82.1% wrong raw across four blind
      rater pools. `verify/` decides what reaches a pull request, and it may not import this module.
IMPORTS: types.finding, types.verdict. stdlib json, subprocess, urllib.
CONSUMED BY: `serve/commands/run_review.py`. NEVER `verify/` — rule 7 forbids it.
"""

from __future__ import annotations

import json
import re

from quantamind.infer.diff_cap import capped
from quantamind.infer.vertex import (
    MODEL,
    InferenceFailed,
    endpoint,
    post,
)
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.finding import Finding
from quantamind.types.spend import Spend, measured

MAX_FINDINGS = 8
MAX_DIFF_CHARS = 120_000

PROMPT = """You are reviewing part of a pull request. Report only defects a maintainer must fix
before merging: logic errors, missing error handling, concurrency hazards, security problems,
API contract violations, data-handling mistakes.

Do not report style, formatting, naming, test coverage or documentation unless the change is
actually incorrect. Do not restate what the diff does. Do not speculate about code you cannot
see in the diff.

Report at most {max_findings}. If the change looks correct, return an empty list -- that is a
valid and useful answer.

For each defect quote the EXACT line from the diff that is wrong. Do not give a line number.

{context}Unified diff:
```
{diff}
```

Respond with ONLY a JSON array of objects, each:
{{"path": "the file", "quote": "the exact line copied from the diff", "claim": "one sentence
naming the defect and why it is wrong", "fix": "the corrected line"}}"""


def _findings(text: str, allowed: set[str]) -> list[Finding]:
    """Parse the reply, keeping only findings about files the ranker actually selected.

    **A finding about a file we did not send is DISCARDED, not published.** The model has been
    observed attaching a claim to an unrelated path, and a claim about code nobody showed it cannot
    have been read off the diff.
    """
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise InferenceFailed(f"no JSON array in reply: {text[:120]!r}")
    try:
        rows = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise InferenceFailed(f"reply is not JSON: {exc}") from None

    out: list[Finding] = []
    for row in rows[:MAX_FINDINGS]:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path", "")).strip()
        if path not in allowed:
            continue
        try:
            out.append(
                Finding(
                    path=path,
                    quote=str(row.get("quote", "")),
                    claim=str(row.get("claim", "")),
                    fix=str(row.get("fix", "")),
                )
            )
        except ValueError:
            # A row missing its quote or claim is dropped, not coerced into a Finding with an
            # empty field: an unanchored finding is exactly what design thirteen removed.
            continue
    return out


def read(
    diff: str,
    paths: list[str],
    *,
    project: str,
    context: str = "",
    location: str = "us-central1",
    gcloud: str = "gcloud",
    model: str = MODEL,
    route: ModelRoute | None = None,
) -> tuple[list[Finding], Spend]:
    """Findings about `paths` only. Raises `Unavailable` when there are no credentials.

    `context` is prose about the change's shape, already rendered by
    `render/blocks/shape_line.py` and passed in by `serve/`. **IT IS A STRING THIS LAYER DOES NOT
    BUILD**, because `render/` sits to the right of `infer/` and rule 7 forbids reaching for it.
    Empty is the supported case and leaves the prompt exactly as it was before shape was measured.
    """
    if not paths:
        return [], Spend()
    url, auth = endpoint(route, project=project, location=location, model=model, gcloud=gcloud)
    prompt = PROMPT.format(
        max_findings=MAX_FINDINGS, diff=capped(diff, MAX_DIFF_CHARS), context=context
    )
    answer = post(
        url,
        auth,
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 32768},
        },
    )
    candidates = answer.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise InferenceFailed(f"no candidates in reply: {str(answer)[:160]}")
    first = candidates[0]
    finish = first.get("finishReason") if isinstance(first, dict) else None
    if finish != "STOP":
        # A truncated reply reads as "the model found fewer defects", which is the failure shape
        # this project keeps mistaking for a result. Raised, never trimmed and continued past.
        raise InferenceFailed(f"finishReason {finish!r}, not STOP — the review is incomplete")
    parts = first.get("content", {}).get("parts", [{}])
    elapsed = answer.get("_ms", 0)
    return _findings(str(parts[0].get("text", "")), set(paths)), measured(
        answer, elapsed if isinstance(elapsed, int) else 0
    )
