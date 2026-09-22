"""Read a `pull_request` delivery into a `Review`, including who opened it.

WHAT: `reviewed(payload)` returns the `Review` a pull request delivery asks for, or `Ignore` naming
      why there is nothing to review.
WHY:  **THE AUTHOR IS WHAT BILLING DECIDES ON, AND THIS WAS THE PLACE IT WAS BEING THROWN AWAY.**
      Seats are held per developer, so the reviewer must say who opened the pull request. Before
      this, only `repository.full_name`, `number` and `head.sha` were read, and the author, the
      repository's visibility and the installation were discarded at the first hop.

      **SPLIT OUT OF `serve/webhook_github.py`**, which sat at 195 of its 200 lines: that module
      authenticates and routes a delivery; this one reads the pull request out of it. AGENTS.md
      rule 4: split by concern rather than raise the cap.

      **A BOT IS NAMED BY GITHUB, NOT GUESSED FROM A LOGIN.** `user.type == "Bot"` is the forge's
      own statement. Matching `[bot]` in a login would miss a bot account named otherwise and
      would catch a human who chose that name.
IMPORTS: types.forge.delivery. Leftward only.
CONSUMED BY: `serve/webhook_github.py`.
"""

from __future__ import annotations

from typing import Any

from quantamind.types.forge.delivery import Ignore, Review

REVIEWABLE_ACTIONS = frozenset({"opened", "synchronize", "reopened", "ready_for_review"})


def reviewed(payload: dict[str, Any]) -> Review | Ignore:
    """The review a `pull_request` delivery asks for, or why it asks for none."""
    action = str(payload.get("action") or "")
    if action not in REVIEWABLE_ACTIONS:
        return Ignore(f"action {action!r} does not change the code under review")

    pull = payload.get("pull_request")
    repository = payload.get("repository")
    if not isinstance(pull, dict) or not isinstance(repository, dict):
        return Ignore("payload carried no pull_request or repository object")
    if pull.get("draft") is True:
        return Ignore("the pull request is a draft")

    repo = str(repository.get("full_name") or "")
    number = pull.get("number")
    head_sha = str((pull.get("head") or {}).get("sha") or "")
    if not repo or not isinstance(number, int) or not head_sha:
        return Ignore(f"incomplete payload: repo={repo!r} number={number!r} head={head_sha[:8]!r}")

    user = _object(pull.get("user"))
    owner = _object(repository.get("owner"))
    installation_id = _object(payload.get("installation")).get("id")
    author_id = user.get("id")
    return Review(
        repo=repo,
        number=number,
        head_sha=head_sha,
        author_id=str(author_id) if isinstance(author_id, int) else "",
        author_login=str(user.get("login") or ""),
        author_is_bot=user.get("type") == "Bot",
        # Anything but an explicit False is private — see `Review.private`.
        private=repository.get("private") is not False,
        account=str(owner.get("login") or ""),
        installation_id=installation_id if isinstance(installation_id, int) else 0,
    )


def _object(value: Any) -> dict[str, Any]:
    """`value` when the payload put an object there, else empty — never `None` to `.get()` on."""
    return value if isinstance(value, dict) else {}
