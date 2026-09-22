"""Every way a reviewed pull request can end, and what each one does to the reserved credit.

WHAT: `serve/review/gate.review_pull_request` with `admit` and `deliver` stubbed, asserting the
      outcome billing is told on every exit, and that a free review never calls a model.
WHY:  **A RESERVATION LEFT OPEN CHARGES THE CUSTOMER FOR A REVIEW THAT NEVER HAPPENED.** Every exit
      — posted, quiet, duplicate, model silent, crashed — must settle, and only a review that
      reached someone and consulted the model may keep its charge.

      **FREE MEANS NO MODEL**, enforced by running the pipeline with inference switched off. The
      test reads the settings the pipeline actually received, not a flag this module sets.
IMPORTS: pytest, quantamind.serve.review.{gate,admission}, quantamind.types.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

from typing import Any

import pytest

from quantamind.serve.review import gate
from quantamind.types.admission.decision import Admission, Mode
from quantamind.types.admission.model_route import GeminiKey, OurVertex
from quantamind.types.forge.delivery import Review
from quantamind.types.review import Delivered, Outcome
from quantamind.types.settings import Settings

REVIEW = Review("acme/widgets", 3, "abc1234", author_id="1", author_login="bob", private=False)
SETTINGS = Settings(inference_enabled=True, inference_project="p", max_requests=3)
FULL = Admission(Mode.FULL, "full", reservation_key="k1", model_route=OurVertex("p"))


def _run(
    monkeypatch: pytest.MonkeyPatch, admission: Admission, result: Delivered | Exception
) -> tuple[list[str], list[Any]]:
    settled: list[str] = []
    ran: list[Any] = []
    monkeypatch.setattr(gate, "admit", lambda review, settings: admission)
    monkeypatch.setattr(gate, "settle", lambda a, s, outcome: settled.append(outcome))

    def fake_deliver(
        repo: str, number: int, sha: str, settings: Settings, footer: str, route: Any = None
    ) -> Delivered:
        ran.append((settings, footer, route))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(gate, "deliver", fake_deliver)
    return settled, ran


def _done(outcome: Outcome, consulted: bool = True) -> Delivered:
    return Delivered(outcome, ("a.py",), (), "body", consulted)


@pytest.mark.parametrize(
    ("outcome", "consulted", "settles"),
    [
        (Outcome.POSTED, True, "consumed"),
        (Outcome.REHEARSED, True, "consumed"),
        (Outcome.POSTED, False, "not_consulted"),
        (Outcome.DUPLICATE, True, "duplicate"),
        (Outcome.NOTHING_TO_SAY, True, "nothing_posted"),
        (Outcome.NO_READABLE_FILES, False, "nothing_posted"),
        (Outcome.NO_FILES, False, "nothing_posted"),
    ],
)
def test_every_exit_settles_and_only_a_delivered_model_review_keeps_its_charge(
    monkeypatch: pytest.MonkeyPatch, outcome: Outcome, consulted: bool, settles: str
) -> None:
    settled, _ = _run(monkeypatch, FULL, _done(outcome, consulted))

    gate.review_pull_request(REVIEW, SETTINGS)

    assert settled == [settles]


def test_a_crash_settles_as_failed_and_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Propagating matters too: the listener leaves the delivery open so GitHub retries it."""
    settled, _ = _run(monkeypatch, FULL, RuntimeError("clone exited 128"))

    with pytest.raises(RuntimeError, match="clone exited 128"):
        gate.review_pull_request(REVIEW, SETTINGS)

    assert settled == ["failed"]


def test_a_free_review_runs_with_inference_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _, ran = _run(monkeypatch, Admission(Mode.FREE, "free_public"), _done(Outcome.POSTED, False))

    gate.review_pull_request(REVIEW, SETTINGS)

    assert [settings.runs_model for settings, _, _ in ran] == [False]


def test_a_full_review_keeps_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _, ran = _run(monkeypatch, FULL, _done(Outcome.POSTED))

    gate.review_pull_request(REVIEW, SETTINGS)

    assert [settings.runs_model for settings, _, _ in ran] == [True]


def test_an_unseated_author_on_a_public_repo_gets_the_footer_naming_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unseated = Admission(
        Mode.FREE, "seat_full_public", author_login="bob", seats_used=2, seats_included=2
    )
    _, ran = _run(monkeypatch, unseated, _done(Outcome.POSTED, False))

    gate.review_pull_request(REVIEW, SETTINGS)

    assert "@bob does not have a QuantaMind seat" in ran[0][1]


def test_a_refusal_never_reaches_the_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    settled, ran = _run(monkeypatch, Admission(Mode.REFUSED, "no_credits"), _done(Outcome.POSTED))

    done = gate.review_pull_request(REVIEW, SETTINGS)

    assert (ran, settled, done.outcome) == ([], [], Outcome.NOT_ENTITLED)


def test_a_byok_review_hands_the_customers_key_to_the_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key must reach every model call. Dropped here, a BYOK customer runs on our model."""
    byok = Admission(Mode.FULL, "full", model_route=GeminiKey("AIza-theirs"))
    _, ran = _run(monkeypatch, byok, _done(Outcome.POSTED))

    gate.review_pull_request(REVIEW, SETTINGS)

    assert [route for _, _, route in ran] == [GeminiKey("AIza-theirs")]
