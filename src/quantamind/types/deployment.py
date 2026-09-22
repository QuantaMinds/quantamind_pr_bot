"""Where this instance runs, and what it is therefore allowed to reach.

WHAT: `Shape` is cloud, on-premises or air-gapped. `Destination` names each thing this product
      talks to. `permit(destination, shape)` returns nothing and raises `NetworkRefused` when the
      shape forbids it.
WHY:  **D7f. AN OUTBOUND CALL THAT FAILS QUIETLY IN A BANK IS A FINDING AGAINST US, NOT A BUG.**
      Air-gapped is not "we happen not to call out" — a deployment that merely lacks a route
      produces timeouts, retries and a review that is late rather than refused, and the customer
      discovers the attempt in their egress logs rather than in our documentation. **The refusal
      must be ours, immediate, and named**, so an operator reading a stack trace sees the shape
      that forbade it and the destination that was wanted.

      **THE CLONE IS THE BOUNDARY, NOT AN EXCEPTION TO IT.** Air-gapped means "Half A only, no
      network beyond the clone": the repository under review must still be readable, because
      without it there is nothing to review at all. Everything else — GitHub's API, inference,
      the metadata server, Jira, Slack, a package index — is refused. That is exactly the
      deterministic half this product argues is the half that carries it.

      **REFUSAL IS A TYPE, NOT A FLAG.** `NetworkRefused` carries the destination and the shape, so
      the message a customer sees names what was attempted rather than saying "network error". A
      boolean `offline=True` checked at seven call sites is seven chances to forget one;
      `scripts/guard/check_network_chokepoint.py` is what makes forgetting fail the build.
IMPORTS: stdlib enum only. Nothing from any layer, because every layer must be able to ask.
CONSUMED BY: `ingest/{github_api,app_auth,google_auth,context.elsewhere}`, `infer/vertex`,
      `verify/releases`, `serve/{web.signin,working_clone}`, `ingest/notify/resend_api`.
"""

from __future__ import annotations

from enum import Enum


class Shape(Enum):
    """How this instance is deployed. **One image; the shape is configuration, not a build.**"""

    CLOUD = "cloud"
    """We run it. Everything is reachable."""

    ON_PREM = "on_prem"
    """They run the same image inside their network. Still reaches their GitHub and their model."""

    AIR_GAPPED = "air_gapped"
    """No network beyond the clone. **Every other destination is refused, not merely unused.**"""


class Destination(Enum):
    """Something outside this process that the product talks to."""

    GIT_REMOTE = "git_remote"
    """Cloning or fetching the repository under review. The one thing air-gapped still permits."""

    GITHUB_API = "github_api"
    """Pull requests, issues, comments, statuses, checks."""

    INFERENCE = "inference"
    """The model. Air-gapped runs the deterministic half and says so."""

    GOOGLE_METADATA = "google_metadata"
    """The instance metadata server, for a service-account token."""

    EXTERNAL_CONTEXT = "external_context"
    """Jira, Slack — D6c's sources, which also need their own egress consent."""

    PACKAGE_INDEX = "package_index"
    """PyPI and friends, read by the release oracle to check a version claim."""

    # **THERE IS NO `PAYMENTS` DESTINATION, AND ITS ABSENCE IS THE POINT.** This service made
    # outbound calls to Stripe until the billing service took ownership of that relationship; it
    # is now TOLD what an account holds over an inbound `POST /entitlement` and initiates nothing.
    # A destination nothing reaches would read as a capability this deployment has, which is the
    # opposite of what this enum is for. See `docs/engineering/STRIPE.md`.

    NOTIFICATIONS = "notifications"
    """Transactional email, through Resend. Outbound only; nothing arrives back on this route.

    **PERMITTED ON-PREM, AND IT IS A DECISION RATHER THAN A DEFAULT.** An
    on-premises operator still has to be told when a review failed. But mail leaves through a
    third party rather than through their own GitHub, so an operator who considers that egress
    unacceptable has one lever: run the air-gapped shape, where this is refused by name before
    the socket opens rather than discovered in their logs afterwards."""


PERMITTED: dict[Shape, frozenset[Destination]] = {
    Shape.CLOUD: frozenset(Destination),
    Shape.ON_PREM: frozenset(Destination) - {Destination.GOOGLE_METADATA},
    Shape.AIR_GAPPED: frozenset({Destination.GIT_REMOTE}),
}
"""What each shape may reach.

**ON-PREM LOSES THE METADATA SERVER AND NOTHING ELSE.** `ingest/google_auth.py` reads a token from
an address that only exists inside Google's fabric; asking for it elsewhere hangs until a timeout,
which is the quiet failure this row exists to remove. Their own credential is configured instead.

**AIR-GAPPED KEEPS ONLY THE CLONE**, which is not a loophole: with no repository there is nothing
to review, and the whole deterministic half runs against a clone and nothing else."""


class NetworkRefused(RuntimeError):
    """This deployment shape forbids reaching that destination. **Ours, immediate, and named.**"""

    def __init__(self, destination: Destination, shape: Shape) -> None:
        super().__init__(
            f"{shape.value} deployment refuses {destination.value}: this instance is configured "
            f"not to reach it. Nothing was sent. Permitted here: "
            f"{', '.join(sorted(d.value for d in PERMITTED[shape]))}."
        )
        self.destination, self.shape = destination, shape


SHAPE_VARIABLE = "QUANTAMIND_DEPLOYMENT_SHAPE"


def current() -> Shape:
    """The shape this process is deployed as. **An unrecognised value refuses.**

    Read from the environment rather than threaded through nine call signatures, because the
    alternative is a `Shape` parameter on every low-level network function and on everything that
    calls them — and a parameter somebody can forget to pass is the same hazard as a flag somebody
    can forget to check. `types/settings.py:Settings.shape` is the same read for code that already
    holds settings; this is for the call sites that do not.

    **AN UNKNOWN NAME RAISES.** Defaulting a typo to `cloud` would turn a misconfigured air-gapped
    deployment into one that reaches the network, which is precisely what this module prevents.
    """
    import os

    return named(os.environ.get(SHAPE_VARIABLE) or Shape.CLOUD.value)


class NotADeploymentShape(ValueError):
    """The configured shape is not one we have. **Refused rather than defaulted.**"""

    def __init__(self, raw: str) -> None:
        super().__init__(
            f"{SHAPE_VARIABLE}={raw!r} is not a deployment shape; expected one of "
            f"{', '.join(s.value for s in Shape)}"
        )
        self.raw = raw


def named(raw: str) -> Shape:
    """A configured string as a shape. **A name we do not have raises rather than defaulting.**

    Lives here rather than on `Settings` so the refusal is one function with one test, wherever the
    string came from — an environment variable, a settings object, or a command line.
    """
    try:
        return Shape(raw)
    except ValueError:
        raise NotADeploymentShape(raw) from None


def permit(destination: Destination, shape: Shape | None = None) -> None:
    """Raise unless the shape allows reaching `destination`. **Called BEFORE the socket opens.**

    Returns None so a call site reads as a statement rather than a condition — a boolean would
    invite `if permitted(...)`, and a caller who forgets the `if` gets a call that proceeds.
    `shape` defaults to `current()`; tests pass it explicitly.
    """
    where = current() if shape is None else shape
    if destination not in PERMITTED[where]:
        raise NetworkRefused(destination, where)
