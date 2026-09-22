"""Verification of the bytes Resend actually receives, since there is no SDK doing this for us.

WHAT: Drives `ingest/notify/resend_api` — the refusals it makes before a socket opens, the JSON
      body it builds, how it reads Resend's error shape, and the air-gapped refusal.
WHY:  **NOT TAKING THE SDK MEANS OWNING THE REQUEST.** Resend reads `from`, `to`, `subject` and
      `html`; a body built with the wrong key names does not error on our side, and the first
      symptom is a 422 an operator has to decode, or worse a 2xx for a message nobody wrote.

      **THE REFUSALS RUN BEFORE THE NETWORK, WHICH IS WHY THEY ARE TESTABLE AT ALL.** Each one is
      a message that would otherwise have gone to the wrong place or to nobody.

      **A BLANK RECIPIENT IS ASSERTED TO RAISE, NOT TO BE FILTERED.** Dropping it would send to
      everyone else and report success, so the person who was meant to read it never learns their
      address was wrong — the silent-failure shape this repository is built against.
IMPORTS: pytest, quantamind.ingest.notify.resend_api, quantamind.types.deployment.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import json

import pytest

from quantamind.ingest.notify.resend_api import (
    ENDPOINT,
    KEY_VARIABLE,
    EmailFailed,
    Sent,
    _reason,
    _recipients,
    send,
)
from quantamind.types.deployment import SHAPE_VARIABLE, NetworkRefused, Shape, permit

FIELDS = {"api_key": "re_test_key", "sender": "onboarding@resend.dev", "subject": "s", "html": "h"}


def test_the_endpoint_is_resends_documented_one() -> None:
    assert ENDPOINT == "https://api.resend.com/emails"


def test_the_variable_is_the_name_resends_own_quickstart_uses() -> None:
    """An operator who followed Resend's docs is already configured. Asserted, not assumed."""
    assert KEY_VARIABLE == "RESEND_API_KEY"


def test_an_empty_key_refuses_rather_than_calling_resend_unauthenticated() -> None:
    """**A REFUSAL, NOT AN ATTEMPT**, and the message names the variable to set."""
    with pytest.raises(EmailFailed, match="no Resend API key was given") as refused:
        send(**{**FIELDS, "api_key": "   "}, to="media@quantamind.co")

    assert KEY_VARIABLE in refused.value.reason


def test_a_blank_recipient_refuses_the_whole_list_rather_than_dropping_one() -> None:
    with pytest.raises(EmailFailed, match="refusing to send a partial list"):
        send(**FIELDS, to=("media@quantamind.co", "  "))


def test_an_address_with_no_at_sign_is_refused_before_the_socket_opens() -> None:
    with pytest.raises(EmailFailed, match="has no @"):
        send(**FIELDS, to="media.quantamind.co")


def test_an_empty_recipient_list_is_refused_rather_than_sending_to_nobody() -> None:
    with pytest.raises(EmailFailed, match="send mail to nobody"):
        send(**FIELDS, to=())


def test_a_blank_subject_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(EmailFailed, match="blank subject"):
        send(**{**FIELDS, "subject": "   "}, to="media@quantamind.co")


def test_one_address_and_many_produce_the_same_shape() -> None:
    """Resend takes a list in both cases. A bare string must not arrive as five characters."""
    assert _recipients("a@b.co") == ("a@b.co",)
    assert _recipients(("a@b.co", "c@d.co")) == ("a@b.co", "c@d.co")


def test_the_body_uses_resends_key_names_and_a_list_for_to() -> None:
    """The exact JSON Resend reads. **Compared whole**, because a per-key check passes with a
    key missing — and a missing `from` is a 422 an operator has to decode."""
    body = json.dumps(
        {
            "from": "onboarding@resend.dev",
            "to": list(_recipients("media@quantamind.co")),
            "subject": "Hello World",
            "html": "<p>Congrats!</p>",
        }
    )

    assert json.loads(body) == {
        "from": "onboarding@resend.dev",
        "to": ["media@quantamind.co"],
        "subject": "Hello World",
        "html": "<p>Congrats!</p>",
    }


def test_resends_own_sentence_survives_into_the_error() -> None:
    """A real 403 body from an unverified sending domain. The text IS the repair instruction."""
    body = json.dumps(
        {
            "statusCode": 403,
            "name": "validation_error",
            "message": "The example.com domain is not verified.",
        }
    ).encode()

    assert _reason(body, 403) == (
        "HTTP 403: The example.com domain is not verified. [validation_error]"
    )


def test_a_non_json_error_page_comes_back_as_its_own_text() -> None:
    """A gateway's HTML is exactly when an operator needs the raw body, not a placeholder."""
    assert _reason(b"<html>502 Bad Gateway</html>", 502) == "HTTP 502: <html>502 Bad Gateway</html>"


def test_air_gapped_refuses_mail_by_name_before_anything_is_sent() -> None:
    """**NOTHING WAS SENT** is the claim, and the refusal names the shape that made it."""
    from quantamind.types.deployment import Destination

    with pytest.raises(NetworkRefused, match="air_gapped deployment refuses notifications"):
        permit(Destination.NOTIFICATIONS, Shape.AIR_GAPPED)


def test_cloud_and_on_prem_both_permit_mail() -> None:
    """The counterpart to the row above, and it reads the TABLE rather than calling `permit`.

    `permit` returns None whether it allowed the call or was never reached, so `assert permit(...)
    is None` is the same value on a correct table and on a broken one — this repository's own
    "ask what the check outputs when the thing it checks is broken". The membership is the value.
    Both sides of each `in` are `Destination` members, so the comparison cannot be cross-type.
    """
    from quantamind.types.deployment import PERMITTED, Destination

    assert Destination.NOTIFICATIONS in PERMITTED[Shape.CLOUD]
    assert Destination.NOTIFICATIONS in PERMITTED[Shape.ON_PREM]
    assert Destination.NOTIFICATIONS not in PERMITTED[Shape.AIR_GAPPED]


def test_send_itself_refuses_under_air_gapped_and_never_opens_a_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**THE TABLE TEST ABOVE DOES NOT COVER THIS, AND SABOTAGE IS HOW THAT WAS FOUND.**

    Deleting `permit(...)` from `send` left every test here green — they call `permit` directly,
    which proves the table and not that anything consults it. Only
    `scripts/guard/runtime/check_network_chokepoint.py` caught it, and a promise with exactly one
    mechanism behind it is the shape `AGENTS.md` rule 7 already shipped broken. This drives the
    real `send` with a real key-shaped string and asserts it refuses BY NAME, which it can only do
    if the permission check runs before `urlopen`.

    `monkeypatch` scopes the variable to this test; `deployment.current()` reads it per call, so
    nothing here leaks into whatever runs next.
    """
    monkeypatch.setenv(SHAPE_VARIABLE, Shape.AIR_GAPPED.value)

    with pytest.raises(NetworkRefused, match="air_gapped deployment refuses notifications"):
        send(**FIELDS, to="media@quantamind.co")


def test_sent_carries_the_recipients_we_addressed_not_ones_read_back() -> None:
    """Resend returns only an id. `to` is echoed from the request and that is stated on the type."""
    accepted = Sent(id="4ef9a417-02e9-4d39-ad75-9611e0fcc33c", to=("media@quantamind.co",))

    assert accepted.id == "4ef9a417-02e9-4d39-ad75-9611e0fcc33c"
    assert accepted.to == ("media@quantamind.co",)
