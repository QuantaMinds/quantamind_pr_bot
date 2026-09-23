"""What a pull request is told when it is not reviewed — one true sentence per reason.

WHAT: `render/not_entitled.{refusal,seat_footer}` for every refusal reason billing can return.
WHY:  **THIS IS THE PRODUCT'S MAIN SALES SURFACE, NOT AN ERROR PAGE.** Every developer on an account
      that has not paid, or has run out of seats or credits, arrives here first.

      **THE FIRST VERSION SAID THE SAME THING UNDER EVERY REASON** — "private repositories are on a
      paid plan" — including for a removed installation and a repository with too few stars. So
      each reason is asserted to carry its OWN fix and not another reason's.

      **IT IS STILL A CUSTOMER-FACING COMMENT**, so `docs/product/comment-golden-rules.md` applies:
      never mention our method.
IMPORTS: pytest, quantamind.render.not_entitled, quantamind.types.admission.decision.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import pytest

from quantamind.render.not_entitled import SITE, refusal, seat_footer
from quantamind.types.admission.decision import Admission, Mode


def refused(reason: str, **over: object) -> Admission:
    fields: dict[str, object] = {
        "author_login": "carol",
        "seats_used": 2,
        "seats_included": 2,
        "resets_at": "2026-11-01T00:00:00.000Z",
    }
    fields.update(over)
    return Admission(Mode.REFUSED, reason, **fields)  # type: ignore[arg-type]


REASONS = ["private_needs_plan", "seat_full", "no_credits", "byok_key_missing"]


def test_each_reason_gives_its_own_way_forward_and_not_another_one() -> None:
    bodies = {reason: refusal(refused(reason)) for reason in REASONS}

    assert f"{SITE}/pricing" in bodies["private_needs_plan"]
    assert f"{SITE}/account" not in bodies["private_needs_plan"]
    assert "does not have a QuantaMind seat" in bodies["seat_full"]
    assert "used all of its review credits" in bodies["no_credits"]
    assert "Gemini API key" in bodies["byok_key_missing"]
    # The defect this replaced: one reason's sentence appearing under another.
    assert all("private repositories are on a paid plan" not in bodies[r] for r in REASONS[1:])


def test_a_seat_refusal_names_the_developer_and_the_count() -> None:
    body = refusal(refused("seat_full", author_login="carol", seats_used=5, seats_included=5))

    assert "@carol does not have a QuantaMind seat" in body
    assert "5 seat(s) and all 5 are in use" in body


def test_an_account_level_refusal_names_nobody() -> None:
    """No plan, no credits and no key are the account's problem, not the author's."""
    names = [
        r
        for r in ("private_needs_plan", "no_credits", "byok_key_missing")
        if "@carol" in refusal(refused(r))
    ]

    assert names == []


def test_the_credit_refusal_says_when_it_resets_in_words() -> None:
    body = refusal(refused("no_credits", resets_at="2026-11-01T00:00:00.000Z"))

    assert "resets on 1 November 2026" in body


def test_every_refusal_says_nothing_was_read() -> None:
    """Silence and approval must never look alike — the defect this product exists to refuse."""
    assert [r for r in REASONS if "nothing was read" not in refusal(refused(r))] == []


@pytest.mark.parametrize("leak", ["rank", "history", "budget", "decile", "percentile", "top three"])
def test_no_refusal_mentions_our_method(leak: str) -> None:
    assert [r for r in REASONS if leak in refusal(refused(r)).lower()] == []


def test_an_unknown_reason_is_named_rather_than_dressed_as_a_known_one() -> None:
    body = refusal(refused("something_new"))

    assert "could not be reviewed (something_new)" in body


def test_an_empty_reason_is_refused() -> None:
    with pytest.raises(ValueError, match="must carry its reason"):
        refusal(refused("   "))


def test_the_free_review_footer_names_who_needs_a_seat() -> None:
    footer = seat_footer(
        Admission(Mode.FREE, "seat_full_public", author_login="bob", seats_used=3, seats_included=3)
    )

    assert "@bob does not have a QuantaMind seat (3 of 3 in use)" in footer
    assert f"{SITE}/account" in footer


def test_the_links_come_from_configuration_not_from_a_literal() -> None:
    """A staging or on-prem deployment must not send a customer to the production site."""
    body = refusal(refused("no_credits"), "https://review.acme.internal")
    footer = seat_footer(
        Admission(Mode.FREE, "seat_full_public", author_login="bo"), "https://review.acme.internal"
    )

    assert "https://review.acme.internal/account" in body
    assert "https://review.acme.internal/account" in footer
    assert "quantamind.co" not in body
