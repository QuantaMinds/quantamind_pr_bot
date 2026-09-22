"""One authenticated call to Resend, so the key is used in one place and the failure has words.

WHAT: `send(...)` posts one email and returns the id Resend assigned it. `EmailFailed` carries
      the call and what Resend said about it. `Sent` is the id plus the recipients it went to.
WHY:  **NO `resend` SDK, AND THE DEPENDENCY COUNT STAYS AT ZERO.** `pyproject.toml` declares
      `dependencies = []`. What this needs is a JSON POST with a bearer token; the SDK would
      arrive with its own HTTP client and its own retry policy, in a product whose deployment
      story includes air-gapped. This service's Stripe client made the same argument against
      the Stripe SDK before billing moved out (`docs/engineering/STRIPE.md`), and this is the
      weaker API of the two, so the case is stronger.

      **THE KEY IS A PARAMETER AND IS NEVER READ FROM `Settings`.** `types/settings.py` states
      the rule -- *"a credential in a settings object reaches a log or a config dump the first
      time anybody prints one"* -- and `quantamind config` prints that object. It is read through
      `types/dotenv.credential` at the command, beside the Stripe key, and passed down.

      **`permit()` IS CALLED BEFORE THE SOCKET OPENS.** An air-gapped deployment refuses mail by
      name rather than timing out against a US mail provider from inside somebody's network.
      `scripts/guard/runtime/check_network_chokepoint.py` fails the build if that line is removed.

      **IT RAISES ON EVERY NON-2XX AND CARRIES RESEND'S OWN SENTENCE.** Resend's error bodies say
      which thing was wrong -- an unverified sending domain, a malformed address, an expired key
      -- and collapsing that into "email failed" throws away the only text that distinguishes our
      bug from the account's configuration. Returning a value on failure is how a broken call
      becomes a quiet no-op, which this project has already paid for four times.

      **THE ID IS RETURNED RATHER THAN LOGGED, AND ACCEPTANCE IS NOT DELIVERY.** A 2xx means
      Resend queued it; the inbox is a separate event this process never sees. The caller gets
      the id so it can say what it actually knows, which is the id and nothing past it.
IMPORTS: stdlib (json, urllib, dataclasses) and `types.deployment`. Leftward only.
CONSUMED BY: `serve/commands/run_email.py`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from quantamind.types.deployment import Destination, permit

ENDPOINT = "https://api.resend.com/emails"
TIMEOUT_S = 30

KEY_VARIABLE = "RESEND_API_KEY"
"""The name the operator writes in `.env`. **DECLARED HERE, READ IN ONE PLACE, NAMED ON FAILURE.**
Resend's own documentation calls it this, and matching it means an operator who follows their
quickstart is already configured. The refusal below prints this string so a `.env` that holds the
wrong name produces the variable to fix rather than "unauthorized"."""


class EmailFailed(RuntimeError):
    """A Resend call that did not return 2xx, or a refusal before one was attempted."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"POST {ENDPOINT}: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Sent:
    """What we know after Resend accepted the message. **Not that anybody received it.**"""

    id: str
    """Resend's own id for the message. The only handle their dashboard can be searched by."""

    to: tuple[str, ...]
    """Who it was addressed to. Echoed back from the request, NOT read from the response --
    Resend does not return the recipients, and inventing them from a response we did not read
    would be the fabrication this project refuses elsewhere."""


def _reason(body: bytes, status: int) -> str:
    """Resend's own message, or the raw body when it is not the error shape we expect.

    **THE FALLBACK RETURNS THE BODY, NOT A PLACEHOLDER.** A gateway's HTML error page is not JSON
    and is exactly the case where an operator needs to see what actually came back.
    """
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return f"HTTP {status}: {body[:400].decode('utf-8', 'replace')}"
    if isinstance(parsed, dict):
        said = str(parsed.get("message") or parsed.get("error") or "")
        name = str(parsed.get("name") or "")
        if said:
            return f"HTTP {status}: {said}" + (f" [{name}]" if name else "")
    return f"HTTP {status}: {body[:400].decode('utf-8', 'replace')}"


def _recipients(to: str | tuple[str, ...]) -> tuple[str, ...]:
    """Addresses as a tuple, with empty entries refused rather than silently dropped.

    **AN ADDRESS THAT IS ONLY WHITESPACE IS A REFUSAL, NOT A FILTER.** Dropping it would send the
    message to everyone else and report success, so the one recipient who was supposed to read it
    never learns that their address was malformed.
    """
    many = (to,) if isinstance(to, str) else tuple(to)
    if not many:
        raise EmailFailed("no recipient was named; refusing to send mail to nobody")
    for address in many:
        if not address.strip():
            raise EmailFailed(f"recipient {address!r} is blank; refusing to send a partial list")
        if "@" not in address:
            raise EmailFailed(f"recipient {address!r} has no @; Resend would reject it")
    return many


def send(
    *,
    api_key: str,
    sender: str,
    to: str | tuple[str, ...],
    subject: str,
    html: str,
) -> Sent:
    """Send one email. `Sent` on 2xx, `EmailFailed` on anything else.

    `sender` must be an address on a domain verified in the Resend account, or Resend's own
    `onboarding@resend.dev`, which delivers ONLY to the address that owns the account.
    """
    if not api_key.strip():
        raise EmailFailed(
            f"no Resend API key was given. This is a refusal rather than an unauthenticated "
            f"attempt: set {KEY_VARIABLE} in the environment or in the repository `.env`"
        )
    recipients = _recipients(to)
    if not subject.strip():
        raise EmailFailed("no subject; a blank subject is a spam signal, not a default")
    permit(Destination.NOTIFICATIONS)
    body = json.dumps(
        {"from": sender, "to": list(recipients), "subject": subject, "html": html}
    ).encode()
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "quantamind",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            answered = response.read()
    except urllib.error.HTTPError as exc:
        raise EmailFailed(_reason(exc.read(), exc.code)) from None
    except urllib.error.URLError as exc:
        raise EmailFailed(f"could not reach Resend: {exc.reason}") from None
    except TimeoutError:
        raise EmailFailed(f"Resend did not answer within {TIMEOUT_S}s") from None

    try:
        # A heterogeneous object we do not own the schema for; the id is the field we named.
        parsed: Any = json.loads(answered)
    except json.JSONDecodeError as exc:
        raise EmailFailed(f"Resend answered 2xx with non-JSON: {exc}") from None
    identifier = parsed.get("id") if isinstance(parsed, dict) else None
    if not isinstance(identifier, str) or not identifier:
        raise EmailFailed(f"Resend accepted the message but named no id: {answered[:200]!r}")
    return Sent(id=identifier, to=recipients)
