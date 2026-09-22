"""Verify a GitHub webhook, decide whether it is ours to act on, and say what to do with it.

WHAT: `verify()` authenticates a delivery against the shared secret, and `interpret()` turns an
      authenticated payload into one of four outcomes — review, installed, withdrawn, or ignored.
WHY:  **This is the only untrusted input the product accepts.** Everything else comes from git or
      from a repository we were pointed at; this arrives from the network from anyone who finds the
      URL. So the two dangerous decisions — is this really GitHub, and is this ours to act on —
      are pure functions over bytes, testable exhaustively without a socket.

      **An absent secret RAISES. It does not skip verification.** "No secret configured, so accept
      everything" is how a webhook endpoint becomes an open command channel, and it is the default
      that reads as working perfectly in every test that supplies a secret.

      **The comparison is constant-time, and NO TEST CAN SEE THAT.** Replacing `compare_digest`
      with `==` leaves every test in `tests/unit/test_webhook_github.py` passing — verified by doing
      it. A byte-by-byte compare leaks the expected digest through response timing, which is a slow
      but real forgery path, and the only things protecting it are this sentence and code review.
      It is written down because a property nothing checks is a property that erodes.

      **VERIFICATION IS NOT REPLAY PROTECTION, and GitHub does not close that gap for us.** Its
      signature covers the body and nothing else — there is no timestamp in it, unlike Stripe's —
      so a captured delivery stays valid forever. `verify()` proves the bytes came from GitHub; it
      cannot prove they are arriving for the first time. That is `store.deliveries`' job, keyed on
      the `X-GitHub-Delivery` GUID, and the caller must use it: this module deliberately does not,
      because the store is to its LEFT and a webhook decision that opened a database would not be a
      pure function.

      **A signature we cannot parse is a rejection, never a pass.** Missing header, wrong prefix,
      odd length, non-hex — each is a distinct reason, returned rather than collapsed into False,
      because "someone is probing us" and "our own secret is misconfigured" need different
      responses from an operator.
IMPORTS: types.forge.delivery — the four outcomes, shared with the Bitbucket parser —
      and serve.pull_request_event, which reads the pull request. Leftward and same-layer only.
CONSUMED BY: the HTTP binding, and nothing else — the decisions here are testable without one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from enum import Enum
from typing import Any

# The four outcomes live in `types/` because a second forge produces the same ones from a
# payload that shares no field names with GitHub's. This module PARSES them; it does not own
# them, and it does not re-export them — every consumer imports them from their one home.
from quantamind.serve.pull_request_event import reviewed
from quantamind.types.forge.delivery import Ignore, Installed, Review, Withdrawn

SIGNATURE_HEADER = "X-Hub-Signature-256"
DELIVERY_HEADER = "X-GitHub-Delivery"
EVENT_HEADER = "X-GitHub-Event"
PREFIX = "sha256="
DIGEST_HEX_LEN = 64
# The only event that can produce a review. Everything else is acknowledged and dropped.
REVIEWABLE_EVENT = "pull_request"


class Rejected(Enum):
    """Why a delivery was not accepted. Distinct values because they need distinct responses."""

    NO_SIGNATURE = "no signature header"
    MALFORMED_SIGNATURE = "signature is not sha256=<64 hex chars>"
    BAD_SIGNATURE = "signature does not match the body"


class MisconfiguredSecret(RuntimeError):
    """No webhook secret is configured.

    Raised rather than accepting the delivery. An endpoint that verifies nothing when the secret is
    missing is an open command channel, and every test that supplies a secret passes anyway — which
    is why this is an exception and not a `False`.
    """


def verify(secret: str, body: bytes, signature: str | None) -> Rejected | None:
    """None when the delivery is authentic, otherwise why it was rejected.

    `secret` empty raises: see `MisconfiguredSecret`.
    """
    if not secret:
        raise MisconfiguredSecret(
            "no webhook secret is configured, so no delivery can be authenticated. Refusing to "
            "accept unverified input; set the secret rather than running without one"
        )
    if not signature:
        return Rejected.NO_SIGNATURE
    if not signature.startswith(PREFIX):
        return Rejected.MALFORMED_SIGNATURE
    offered = signature[len(PREFIX) :]
    if len(offered) != DIGEST_HEX_LEN or any(c not in "0123456789abcdefABCDEF" for c in offered):
        return Rejected.MALFORMED_SIGNATURE
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # Constant-time: a byte-by-byte compare leaks the expected digest through response timing.
    return None if hmac.compare_digest(expected, offered.lower()) else Rejected.BAD_SIGNATURE


def sign(secret: str, body: bytes) -> str:
    """The header GitHub would send for this body. Used by tests to build authentic deliveries."""
    if not secret:
        raise MisconfiguredSecret("cannot sign with an empty secret")
    return PREFIX + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


INSTALL_EVENTS = ("installation", "installation_repositories")


# Actions after which the installation can do nothing. **`suspend` BELONGS HERE AND `removed` DOES
# NOT.** A suspended installation still exists and its token still fails, so leaving it covered
# turns every later delivery into a clone that cannot authenticate -- which a customer reads as us
# being broken rather than as us being switched off. `removed` is per-repository and leaves the
# installation alive, so it is a smaller fact and rides on `Installed.no_longer_covered`.
GONE_ACTIONS = frozenset({"deleted", "suspend"})


def _named(payload: dict[str, Any]) -> tuple[str, int, int, str]:
    """Who this installation belongs to. A zero or empty field means the delivery did not say."""
    seat = payload.get("installation") or {}
    who = seat.get("account") or {}
    return (
        str(who.get("login", "")),
        int(seat.get("id") or 0),
        int(who.get("id") or 0),
        str(who.get("type", "")),
    )


def _listed(payload: dict[str, Any], *keys: str) -> tuple[str, ...]:
    """Every `full_name` under these payload keys, deduplicated and ordered."""
    found: list[str] = []
    for key in keys:
        for entry in payload.get(key) or []:
            if isinstance(entry, dict) and entry.get("full_name"):
                found.append(str(entry["full_name"]))
    return tuple(sorted(set(found)))


def _installed(payload: dict[str, Any]) -> Installed | Withdrawn | Ignore:
    """An installation delivery, or why it could not be read."""
    account, installation_id, account_id, kind = _named(payload)
    if not account:
        return Ignore("installation payload names no account")
    action = str(payload.get("action", ""))
    if action in GONE_ACTIONS:
        # **NO REPOSITORY LIST IS READ HERE, AND THAT IS NOT AN OVERSIGHT.** GitHub omits it on
        # `deleted`, and every repository under the account stops being covered at the same moment
        # anyway, so naming a subset would describe less than what happened.
        return Withdrawn(account, action, installation_id)
    covered = _listed(payload, "repositories", "repositories_added")
    dropped = _listed(payload, "repositories_removed")
    if not covered and not dropped and action != "removed":
        # **AN INSTALLATION THAT LISTS NOTHING IS NOT A TENANT WITH NO REPOSITORIES.** GitHub omits
        # the list on some actions, and provisioning from an empty list would look identical to a
        # customer who selected none. Said, not assumed away.
        return Ignore(f"installation {action!r} for {account} lists no repositories")
    # **BOTH DIRECTIONS RIDE ON ONE VALUE.** One `installation_repositories` delivery can add and
    # remove in the same payload; returning only one of them would silently drop half of what the
    # customer just told us.
    return Installed(account, covered, action, dropped, installation_id, account_id, kind)


def interpret(event: str | None, body: bytes) -> Review | Installed | Withdrawn | Ignore:
    """What to do with an AUTHENTICATED delivery. Never called before `verify()` returns None.

    Returns `Ignore` with a reason rather than raising: a ping, a label change and a comment are all
    normal traffic, and an endpoint that errors on them fills a log with things nobody should read.
    """
    if event not in (REVIEWABLE_EVENT, *INSTALL_EVENTS):
        return Ignore(f"event {event!r} is not {REVIEWABLE_EVENT!r} or an installation")
    try:
        payload: Any = json.loads(body)
    except json.JSONDecodeError as exc:
        return Ignore(f"body is not JSON: {exc}")
    if event in INSTALL_EVENTS:
        return _installed(payload) if isinstance(payload, dict) else Ignore("body is not an object")
    if not isinstance(payload, dict):
        return Ignore(f"body is {type(payload).__name__}, not an object")

    return reviewed(payload)
