"""The model asks what would settle its claim, an oracle answers, and the model re-decides.

WHAT: `settle(finding, diff, project)` asks the model whether its finding rests on a fact outside
      the diff and what question would settle it, answers that question from GitHub or PyPI, and
      asks only whether the finding still stands given the answer.
WHY:  **THIS IS THE ONE FILTER THAT CLEARED ITS PRE-REGISTERED BARS, AND IT WAS NEVER IN THE
      PRODUCT.** Measured over design thirteen's 86 real adjudicated findings: 29 of 45 wrong
      findings asked an external question rather than asserting (bar 60%), 21 of those 29 were
      settled (bar 50%), **18 of 45 wrong findings stopped publishing, and 1 of 7 correct findings
      was lost against a chance null of 2.8.**

      **THE MODEL IS NEVER ASKED WHETHER IT WAS RIGHT.** It is asked what would settle the claim,
      handed the answer, and asked whether the finding still stands on it. Asking a model to grade
      its own output is the lever measured five times at 8.5-16.8% retained discrimination; this is
      the opposite move, and of the 21 findings the oracle answered, the model withdrew 16.

      **THE ORACLE ANSWERS WITH A FACT AND NEVER A VERDICT.** "5fda3b95 in actions/setup-python
      carries: v7.0.0, v7." A tool that returns "this looks wrong" is a second model wearing a
      parser's clothes, and five of those have failed here.

      **IT DOES NOT REACH THE SEMANTIC CLASS AND IS NOT EXPECTED TO.** 16 of the 45 asked nothing
      at all — "does this loop terminate" has no authority to ask.
IMPORTS: infer.gemini, types.finding, verify.{external_facts,releases}. Rightmost layer, so both
      sides are allowed here and `verify/` still cannot see `infer/`.
CONSUMED BY: `serve/deep_review.py`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from quantamind.infer.prompt_once import ask as _ask
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.finding import Finding
from quantamind.verify.external_facts import sha_exists, tags_at
from quantamind.verify.release_claims import BOUND, NOT_A_PACKAGE
from quantamind.verify.releases import package_exists, released

NAMES_REPO = re.compile(r"\b([A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*)\b")
NAMES_SHA = re.compile(r"\b([0-9a-f]{7,40})\b")

ASK = """You wrote this code-review finding:

{claim}

Does this finding depend on a fact that is NOT in the diff — a repository's tags, a package index,
or today's date?

Answer with ONLY a JSON object:
{{"external": true or false, "question": "the single factual question that would settle it, or ''"}}

If the finding rests only on the code shown, answer false. Do not judge whether it is correct."""

REDECIDE = """You wrote this code-review finding:

{claim}

You asked: {question}

The answer, from the authoritative source, is:

{fact}

Given that answer, does the finding still stand? Answer with ONLY a JSON object:
{{"stands": true or false, "why": "one short sentence"}}"""


@dataclass(frozen=True, slots=True)
class Settled:
    """What the conversation decided, and the fact it turned on."""

    publishes: bool
    asked: str
    fact: str
    why: str


def _json(text: str) -> dict[str, object]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        got: dict[str, object] = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return got


def answer(question: str, today: str) -> str:
    """The FACT an authority holds, or empty when none can be established. Never a verdict."""
    if re.search(r"\b(today'?s? date|current date|what is today)\b", question, re.I):
        return f"Today's date is {today}."
    shas = [x for x in NAMES_SHA.findall(question) if not x.isdigit()]
    for repo in NAMES_REPO.findall(question):
        if "/" not in repo or not shas:
            continue
        reached, exists = sha_exists(repo, shas[0])
        if not reached:
            continue
        if not exists:
            return f"{shas[0][:8]} is not a commit in {repo}."
        reached, found = tags_at(repo, shas[0])
        if reached:
            return f"{shas[0][:8]} in {repo} carries: {', '.join(found) or 'no tag'}."
    # **THE RELEASE PATH ASKS PyPI DIRECTLY AND DOES NOT ROUTE THROUGH THE VERIFIER.**
    # `adjudicate_release` checks a DISPUTING assertion — "X does not exist" — and a question
    # asserts nothing, so it returned NO_CLAIM for "Was requests==2.32.3 ever published to PyPI?"
    # and the model published a false claim for want of an answer it could have had. That is the
    # same defect the conversational arm's first run had on the SHA path, arriving here because
    # the SHA path was fixed and this one was not.
    for match in BOUND.finditer(question):
        name = match.group(1) or match.group(3) or match.group(6)
        want = match.group(2) or match.group(4) or match.group(5)
        if not name or not want or name.lower() in NOT_A_PACKAGE:
            continue
        reached, has_release = released(name, want)
        if not reached:
            continue
        if has_release:
            return f"{name} {want} is published on PyPI."
        answered, is_package = package_exists(name)
        if answered:
            return (
                f"{name} is on PyPI and has no release {want}."
                if is_package
                else f"There is no package called {name} on PyPI."
            )
    return ""


def settle(
    finding: Finding, *, project: str, today: str, route: ModelRoute | None = None
) -> Settled:
    """Ask, answer, re-decide. Publishes unless the model withdraws given a fact it lacked."""
    asked = _json(_ask(ASK.format(claim=finding.claim), project=project, route=route))
    if not asked.get("external"):
        return Settled(True, "", "", "rests on the code shown")
    question = str(asked.get("question", ""))
    fact = answer(question, today)
    if not fact:
        return Settled(True, question, "", "no authority could answer; not grounds to drop it")
    verdict = _json(
        _ask(
            REDECIDE.format(claim=finding.claim, question=question, fact=fact),
            project=project,
            route=route,
        )
    )
    stands = bool(verdict.get("stands", True))
    return Settled(stands, question, fact, str(verdict.get("why", "")))
