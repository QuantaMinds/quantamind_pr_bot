"""When billing does not answer: who is still reviewed, and that nothing is charged.

WHAT: `serve/review/admission.admit` with `ingest/billing/review_gate.authorize` raising, against a
      real store holding (or not holding) a cached plan.
WHY:  **THIS IS THE ONE PATH THAT GIVES REVIEWS AWAY ON PURPOSE**, so it is pinned exactly: a paying
      account (judged by `verify/paid_access` on the cached plan) is reviewed in full and unmetered;
      an unpaid one gets only what is free. Split from `test_admission.py` at the 200-line cap.
IMPORTS: pytest, quantamind.{ingest.billing.review_gate,serve.review.admission,store,types}.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from quantamind.ingest.billing import review_gate
from quantamind.serve.review import admission
from quantamind.store import tenancy
from quantamind.store.billing import entitlement
from quantamind.store.schema import open_store
from quantamind.types.admission.decision import Mode
from quantamind.types.forge.delivery import Review
from quantamind.types.settings import Settings


def _settings(root: Path, **over: Any) -> Settings:
    fields: dict[str, Any] = {
        "database_path": str(root),
        "billing_url": "http://billing.test",
        "inference_enabled": True,
        "inference_project": "our-project",
    }
    fields.update(over)
    return Settings(**fields)


def _review(**over: Any) -> Review:
    fields: dict[str, Any] = {
        "repo": "acme/widgets",
        "number": 3,
        "head_sha": "abc1234",
        "author_id": "1001",
        "author_login": "alice",
        "private": True,
    }
    fields.update(over)
    return Review(**fields)


def _answers(monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any] | Exception) -> list[Any]:
    sent: list[Any] = []

    def fake(url: str, secret: str, request: dict[str, Any]) -> dict[str, Any]:
        sent.append(request)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(review_gate, "authorize", fake)
    return sent


def _paying(root: Path) -> None:
    conn = open_store(tenancy.shared(root, tenancy.ACCOUNTS))
    try:
        now = int(time.time())
        entitlement.record(
            conn,
            "github",
            "acme",
            tier="team",
            state=entitlement.State.ACTIVE,
            as_of=now,
            valid_through=now + 86_400,
        )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "failure",
    [
        review_gate.BillingUnreachable("timed out"),
        review_gate.BillingRefused("HTTP 401"),
    ],
)
def test_billing_silent_a_paying_account_is_reviewed_in_full_unmetered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _paying(tmp_path)
    _answers(monkeypatch, failure)

    got = admission.admit(_review(), _settings(tmp_path))

    assert (got.mode, got.reason, got.unmetered) == (Mode.FULL, "billing_unreachable", True)
    assert got.reservation_key == "", "nothing may be charged when billing never answered"


def test_billing_silent_an_unpaid_account_gets_only_what_is_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, review_gate.BillingUnreachable("down"))

    public = admission.admit(_review(private=False), _settings(tmp_path))
    private = admission.admit(_review(private=True), _settings(tmp_path))

    assert [(a.mode, a.reason) for a in (public, private)] == [
        (Mode.FREE, "free_public"),
        (Mode.REFUSED, "private_needs_plan"),
    ]
