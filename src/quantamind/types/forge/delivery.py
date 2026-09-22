"""What a forge told us, as a value: review this, we were installed, we were removed, or not ours.

WHAT: `Review`, `Installed`, `Withdrawn` and `Ignore` — the four things an authenticated delivery
      can mean. Pure data; no parsing, no I/O.
WHY:  **THEY LIVE HERE RATHER THAN IN THE PARSER BECAUSE A SECOND FORGE IS COMING.** They were
      defined inside `serve/webhook_github.py`, which made them GitHub's vocabulary by accident.
      Bitbucket arrives through a Forge app rather than a signed webhook and its payload looks
      nothing like GitHub's, but what it *means* is one of these same four things — and
      `serve/review/review_delivery.deliver()` must not learn which forge it is serving.
      `webhook_github` re-exports them, so no existing importer changed.

      **`Withdrawn` IS A FOURTH OUTCOME, NOT A FLAG ON `Installed`.** The same argument the third
      one was added under: "the installation is gone" and "the installation covers these
      repositories" are opposite instructions, and folding them together would make an action
      string load-bearing — which is how a log line becomes control flow.

      **REMOVALS RIDE ON `Installed` TOO, AND THAT IS NOT A CONTRADICTION.** One
      `installation_repositories` delivery can carry `repositories_added` AND
      `repositories_removed`. Returning only one outcome for such a delivery would silently drop
      half of what the customer just told us, which is the defect this codebase refuses
      everywhere. So `Installed.no_longer_covered` carries the per-repository removals and
      `Withdrawn` carries the case where there is nothing left to cover at all.

      **THE DEFAULTS EXIST SO A DELIVERY THAT OMITS A FIELD IS NOT A DELIVERY THAT LIED.** GitHub
      does not send `account.type` on every action and a Forge invocation has no numeric
      installation id at all. A zero here means "the delivery did not say", and no caller may read
      it as an identifier.
IMPORTS: stdlib only (dataclasses). Leftmost layer; imports nothing from this project.
CONSUMED BY: `serve/webhook_github.py` (which re-exports them), `serve/listener.py`,
      `serve/installation/withdrawal.py`, `serve/installation/installed_repos.py`,
      `serve/commands/run_endpoint.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Review:
    """A change we should act on, and who opened it.

    **`private` DEFAULTS TO TRUE.** A payload that did not say is treated as private, so a missing
    field can refuse a free review of public code but can never give one away for private code.

    **THE AUTHOR IS AN ID, NOT A LOGIN.** Billing holds seats by `author_id`; a login is renamed and
    then reused by somebody else, and a seat keyed on it would pass to them. `author_login` is for
    the sentence that names them on the pull request, and nothing else.
    """

    repo: str
    number: int
    head_sha: str
    author_id: str = ""
    author_login: str = ""
    author_is_bot: bool = False
    private: bool = True
    account: str = ""
    installation_id: int = 0

    @property
    def owner(self) -> str:
        """The account the repository belongs to — the one that is billed."""
        return self.account or self.repo.partition("/")[0]


@dataclass(frozen=True, slots=True)
class Installed:
    """An installation, or a change to which repositories it covers.

    `repos` is what the installation covers NOW where the forge tells us that, and what this
    delivery ADDED where it only sends a delta. Acting on a full list is idempotent and
    self-healing; acting on a delta is not, which is why `quantamind reconcile` exists rather
    than this value pretending to be authoritative.
    """

    account: str
    repos: tuple[str, ...]
    action: str
    no_longer_covered: tuple[str, ...] = field(default_factory=tuple)
    """Repositories this delivery says we no longer cover. Empty is the ordinary case."""

    installation_id: int = 0
    account_id: int = 0
    account_kind: str = ""
    """`User` or `Organization` where the forge said so, otherwise empty. Never inferred."""


@dataclass(frozen=True, slots=True)
class Withdrawn:
    """The whole installation is gone — uninstalled, or suspended so it can do nothing.

    **SUSPENSION COUNTS, AND THAT IS A DECISION.** A suspended installation still exists and its
    token still fails, so treating it as covered would turn every delivery into a clone that
    cannot authenticate — a failure the customer sees as us being broken rather than as us being
    switched off. `action` records which of the two it was, because "they left" and "they paused
    us" are different answers to an auditor.
    """

    account: str
    action: str
    installation_id: int = 0


@dataclass(frozen=True, slots=True)
class Ignore:
    """A delivery that authenticated and is not ours to act on. Carries why, for the log."""

    reason: str
