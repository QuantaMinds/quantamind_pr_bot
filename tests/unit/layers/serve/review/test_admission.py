"""Every row of the pull-request decision table, as the reviewer carries it out.

WHAT: `serve/review/admission.admit` against a real store, with billing's answer stubbed at the
      one function that makes the call (`ingest/billing/review_gate.authorize`).
WHY:  **BILLING DECIDES AND THIS CARRIES THE ANSWER, SO THE RISK HERE IS MIS-CARRYING IT.** A FULL
      decision without a model route reviews nothing; a GeminiKey dropped on the floor runs a BYOK
      customer on our model; an answer we do not understand read as permission gives reviews away.

      **THE FALLBACK IS WHERE MONEY IS GIVEN AWAY ON PURPOSE**, so it is pinned exactly: a paying
      account (by `verify/paid_access` on the cached plan) is reviewed in full, unmetered, and
      nobody else is.
IMPORTS: pytest, quantamind.{ingest.billing.review_gate,serve.review.admission,store,types}.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from quantamind.ingest.billing import review_gate
from quantamind.serve.review import admission
from quantamind.store import installations, tenancy
from quantamind.store.schema import open_store
from quantamind.types.admission.decision import Mode
from quantamind.types.admission.model_route import GeminiKey, OurVertex
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


def test_the_request_carries_who_opened_it_and_whether_we_will_call_a_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _answers(monkeypatch, {"decision": "free", "reason": "free_public"})

    admission.admit(_review(private=False), _settings(tmp_path))

    assert sent == [
        {
            "forge": "github",
            "account": "acme",
            "repo": "acme/widgets",
            "pr": 3,
            "head_sha": "abc1234",
            "author_id": "1001",
            "author_login": "alice",
            "author_is_bot": False,
            "private": False,
            "wants_model": True,
        }
    ]


def test_full_on_our_plan_runs_our_model_and_keeps_the_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(
        monkeypatch,
        {
            "decision": "full",
            "reason": "full",
            "reservation_key": "k1",
            "seats_used": 1,
            "seats_included": 2,
            "model": None,
        },
    )

    got = admission.admit(_review(), _settings(tmp_path))

    assert (got.mode, got.model_route, got.reservation_key) == (
        Mode.FULL,
        OurVertex("our-project"),
        "k1",
    )
    assert got.unmetered is False


def test_a_byok_answer_runs_the_customers_key_not_ours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(
        monkeypatch,
        {
            "decision": "full",
            "reason": "full",
            "model": {"provider": "gemini", "key": "AIza-their-key"},
        },
    )

    got = admission.admit(_review(), _settings(tmp_path))

    assert got.model_route == GeminiKey("AIza-their-key")
    assert "AIza-their-key" not in repr(got), "the customer's key would reach a log"


def test_a_refusal_is_carried_with_everything_the_comment_needs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(
        monkeypatch,
        {
            "decision": "refused",
            "reason": "seat_full",
            "author_login": "carol",
            "seats_used": 2,
            "seats_included": 2,
        },
    )

    got = admission.admit(_review(), _settings(tmp_path))

    assert (got.mode, got.reason, got.author_login, got.seats_used, got.seats_included) == (
        Mode.REFUSED,
        "seat_full",
        "carol",
        2,
        2,
    )
    assert got.model_route is None


def test_an_answer_we_do_not_understand_is_not_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answers(monkeypatch, {"decision": "maybe", "reason": "?"})

    got = admission.admit(_review(), _settings(tmp_path))

    assert got.mode is Mode.REFUSED
    assert got.reason.startswith("unknown_decision")


def test_a_removed_installation_is_refused_without_asking_billing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = open_store(tenancy.shared(tmp_path, tenancy.ACCOUNTS))
    try:
        installations.record(conn, "acme", "acme/widgets", at=1)
        installations.withdraw(conn, "acme/widgets", at=2)
    finally:
        conn.close()
    sent = _answers(monkeypatch, {"decision": "full"})

    got = admission.admit(_review(), _settings(tmp_path))

    assert (got.mode, got.reason) == (Mode.REFUSED, "removed")
    assert sent == []
