"""Ask the billing service whether a pull request may be reviewed, then tell it what happened.

WHAT: `authorize(url, secret, request)` returns billing's answer as a mapping; `settle(url, secret,
      key, outcome)` closes a credit reservation. `BillingUnreachable` when we got no answer,
      `BillingRefused` when we got one we cannot use.
WHY:  **THE TWO FAILURES ARE DIFFERENT AND THE CALLER ACTS ON THEM DIFFERENTLY.** No answer — a
      timeout, a refused connection, an air-gapped deployment, an unset URL — means billing is down
      and the caller falls back to the cached entitlement, reviewing a paying account unmetered.
      An answer we cannot use — a 401, a 400, a body that is not JSON — means we are misconfigured,
      and pretending billing was merely down would hide it behind free reviews forever.

      **FIVE SECONDS, NOT THIRTY.** This call sits in front of every review, before the clone. A
      slow billing service must cost a review five seconds and then fall back, not hold GitHub's
      delivery past its own ten-second budget.

      **THE BEARER IS PASSED IN, NEVER READ FROM `Settings`**, which `quantamind config` prints.
IMPORTS: stdlib (json, urllib), types.deployment. Leftward only.
CONSUMED BY: `serve/review/admission.py`, `serve/review/review_delivery.py`.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from quantamind.types.deployment import Destination, NetworkRefused, permit

TIMEOUT_S = 5
AUTHORIZE = "/billing/review/authorize"
SETTLE = "/billing/review/settle"


class BillingUnreachable(RuntimeError):
    """We got no answer. The caller falls back to the cached entitlement."""


class BillingRefused(RuntimeError):
    """We got an answer we cannot use. A configuration fault, not an outage."""


def _post(url: str, secret: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    if not url:
        raise BillingUnreachable("QUANTAMIND_BILLING_URL is unset")
    request = urllib.request.Request(
        f"{url.rstrip('/')}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "User-Agent": "quantamind",
        },
    )
    try:
        # **ASK BEFORE THE SOCKET OPENS.** Air-gapped refuses this by name; that is the fallback
        # path, not an error.
        permit(Destination.BILLING)
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as reply:
            raw = reply.read()
    except NetworkRefused as exc:
        raise BillingUnreachable(str(exc)) from None
    except urllib.error.HTTPError as exc:
        detail = (exc.read() or b"").decode("utf-8", "replace")[:160]
        if exc.code >= 500:
            raise BillingUnreachable(f"HTTP {exc.code} from billing: {detail}") from None
        raise BillingRefused(f"HTTP {exc.code} from billing: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BillingUnreachable(f"could not reach billing: {str(exc)[:160]}") from None
    try:
        loaded = json.loads(raw or b"null")
    except json.JSONDecodeError as exc:
        raise BillingRefused(f"billing answered with something that is not JSON: {exc}") from None
    if not isinstance(loaded, dict):
        raise BillingRefused(f"billing answered {type(loaded).__name__}, not an object")
    return loaded


def authorize(url: str, secret: str, request: dict[str, Any]) -> dict[str, Any]:
    """Billing's decision for one pull request, exactly as it sent it."""
    return _post(url, secret, AUTHORIZE, request)


def settle(url: str, secret: str, reservation_key: str, outcome: str) -> bool:
    """Close a reservation. True when a credit was refunded."""
    got = _post(url, secret, SETTLE, {"reservation_key": reservation_key, "outcome": outcome})
    return got.get("refunded") is True
