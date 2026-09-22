"""Whether one pull request is reviewed, how fully, and whether it costs a credit.

WHAT: `admit(review, settings)` returns an `Admission`. It asks the billing service, which
      decides the author's seat and reserves a credit in one transaction, and falls back to the
      entitlement it last pushed when the service cannot be reached.
WHY:  **THIS IS THE CHECK COMPETITORS MAKE AND WE DID NOT.** CodeRabbit asks whether the author
      holds a seat; Greptile spends a credit per review. Until this module, a pull request was
      decided by `store/installations` alone — repository name only, no author, no subscription —
      so paying changed nothing about whether a review happened.

      **BILLING DECIDES; THIS MODULE ONLY CARRIES THE ANSWER.** Seats and credits must be counted
      atomically across concurrent pull requests, which a SQLite file on a lock-free mount cannot
      do. The billing service holds them in Postgres; the rules are in its `admission.ts`.

      **OUR OUTAGE IS NOT THE CUSTOMER'S BILL.** When billing is unreachable, a paying account —
      judged by `verify/paid_access.decide` on the cached entitlement, the same rule billing
      applies — is reviewed in full on our model, UNMETERED, and the log says so. A misconfigured
      billing call (401, 400) takes the same fallback but is logged as a configuration fault, so it
      cannot hide for months behind reviews that simply stopped being charged.

      **THE INSTALLATION ROW NOW ANSWERS ONE QUESTION: IS THE APP STILL INSTALLED.** Its tier and
      eligibility decided access before; visibility now comes from the webhook at the moment of the
      pull request, and payment from billing.
IMPORTS: ingest.billing.review_gate, store.{billing.entitlement,installations,schema,tenancy},
      types.{admission,dotenv,forge.delivery,settings}, verify.paid_access. Leftward only.
CONSUMED BY: `serve/review/review_delivery.py`.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from quantamind.ingest.billing import review_gate
from quantamind.store import installations, tenancy
from quantamind.store.billing import entitlement
from quantamind.store.schema import open_store
from quantamind.types.admission.decision import Admission, Mode
from quantamind.types.admission.model_route import GeminiKey, ModelRoute, OurVertex
from quantamind.types.dotenv import credential
from quantamind.types.forge.delivery import Review
from quantamind.types.settings import Settings
from quantamind.verify import paid_access

FORGE = "github"
SECRET_VARIABLE = "QUANTAMIND_PROVISION_SECRET"
MODES = {"full": Mode.FULL, "free": Mode.FREE, "refused": Mode.REFUSED}


def admit(review: Review, settings: Settings) -> Admission:
    """Billing's decision for this pull request, or the cached fallback when billing is silent."""
    conn = open_store(tenancy.shared(Path(settings.database_path), tenancy.ACCOUNTS))
    try:
        seat = installations.entitled(conn, review.repo)
        if seat.state is installations.State.REMOVED:
            return Admission(Mode.REFUSED, "removed")
        try:
            answer = review_gate.authorize(
                settings.billing_url, credential(SECRET_VARIABLE), _request(review, settings)
            )
        except review_gate.BillingUnreachable as exc:
            print(f"[admit] {review.repo}#{review.number}: billing unreachable — {exc}", flush=True)
            return _fallback(conn, review, settings)
        except review_gate.BillingRefused as exc:
            print(
                f"[admit] {review.repo}#{review.number}: BILLING MISCONFIGURED — {exc}. "
                "Reviewing from the cached entitlement until this is fixed.",
                flush=True,
            )
            return _fallback(conn, review, settings)
    finally:
        conn.close()
    return _from_answer(answer, review, settings)


# `Any` in the two signatures below: a JSON object as billing sends it, narrowed field by field
# in `_from_answer` rather than trusted as a typed shape we do not own.
def _request(review: Review, settings: Settings) -> dict[str, Any]:
    return {
        "forge": FORGE,
        "account": review.owner,
        "repo": review.repo,
        "pr": review.number,
        "head_sha": review.head_sha,
        "author_id": review.author_id or "0",
        "author_login": review.author_login or "unknown",
        "author_is_bot": review.author_is_bot,
        "private": review.private,
        "wants_model": settings.runs_model,
    }


def _ours(settings: Settings) -> ModelRoute | None:
    """Our model, or None when this deployment runs no inference at all."""
    return OurVertex(settings.inference_project) if settings.runs_model else None


def _from_answer(answer: dict[str, Any], review: Review, settings: Settings) -> Admission:
    mode = MODES.get(str(answer.get("decision")))
    if mode is None:
        # An answer we do not understand is not permission. Refused, and named.
        return Admission(Mode.REFUSED, f"unknown_decision:{answer.get('decision')!r}")
    route: ModelRoute | None = None
    if mode is Mode.FULL:
        model = answer.get("model")
        if isinstance(model, dict) and model.get("provider") == "gemini" and model.get("key"):
            route = GeminiKey(str(model["key"]))
        else:
            route = _ours(settings)
    return Admission(
        mode=mode,
        reason=str(answer.get("reason") or ""),
        author_login=str(answer.get("author_login") or review.author_login),
        seats_used=int(answer.get("seats_used") or 0),
        seats_included=int(answer.get("seats_included") or 0),
        resets_at=str(answer.get("resets_at") or ""),
        reservation_key=str(answer.get("reservation_key") or ""),
        model_route=route,
    )


def _fallback(conn: sqlite3.Connection, review: Review, settings: Settings) -> Admission:
    """What the cached entitlement allows, when billing did not answer.

    **SEATS CANNOT BE CHECKED HERE**, because the seat table lives in billing. A paying account is
    reviewed for any author — the generous reading, which our outage has earned the customer.
    """
    now = int(time.time())
    cover = entitlement.covering(conn, FORGE, review.owner, now=now)
    paid = paid_access.decide(cover, at=now).allowed
    if review.author_is_bot:
        if not paid and review.private:
            return Admission(Mode.REFUSED, "private_needs_plan", author_login=review.author_login)
        return Admission(Mode.FREE, "bot", author_login=review.author_login)
    if paid:
        return Admission(
            Mode.FULL,
            "billing_unreachable",
            author_login=review.author_login,
            model_route=_ours(settings),
            unmetered=True,
        )
    if review.private:
        return Admission(Mode.REFUSED, "private_needs_plan", author_login=review.author_login)
    return Admission(Mode.FREE, "free_public", author_login=review.author_login)


def settle(admission: Admission, settings: Settings, outcome: str) -> None:
    """Tell billing what happened to a reserved credit. Never raises into the caller.

    **A FAILED SETTLE IS LOGGED, NOT RETRIED HERE.** It leaves the credit charged, so the error
    runs against the customer by one credit. It is visible in the ledger as a debit with no refund,
    and it is preferred to holding the delivery open on a second billing call.
    """
    if not admission.reservation_key:
        return
    try:
        refunded = review_gate.settle(
            settings.billing_url, credential(SECRET_VARIABLE), admission.reservation_key, outcome
        )
    except (review_gate.BillingUnreachable, review_gate.BillingRefused) as exc:
        print(f"[admit] settle {admission.reservation_key} ({outcome}) FAILED: {exc}", flush=True)
        return
    if refunded:
        print(f"[admit] refunded {admission.reservation_key}: {outcome}", flush=True)
