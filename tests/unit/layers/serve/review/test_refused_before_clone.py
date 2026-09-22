"""A repository we refuse is never cloned. Ordering, asserted rather than assumed.

WHAT: `deliver()` against a store whose installation row is ineligible, with `ensure` instrumented
      to record whether it was called at all.
WHY:  **THE CHECK USED TO RUN AFTER THE CLONE.** A refused repository was cloned first — a full
      copy of somebody's private source pulled onto our disk and kept, for a review we then
      declined to do. `docs/product/pricing.md` promises "one working copy of your repository, on
      our servers, used for reviewing and nothing else"; holding a clone of a repository we refused
      makes that sentence false, and it is the kind of false that becomes a contract problem rather
      than a credibility one.

      **ORDERING IS INVISIBLE TO EVERY OTHER TEST.** Both orders produce the same `NOT_ENTITLED`
      outcome and the same comment. The only observable difference is whether the network was
      touched, so that is what this asserts.

      Sabotage: move the seat block back below `ensure()` and this fails.
IMPORTS: quantamind.serve.review.review_delivery, quantamind.store.{installations,schema,tenancy},
      quantamind.types.settings.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantamind.serve.review import gate, review_delivery
from quantamind.types.forge.delivery import Review
from quantamind.types.review import Outcome
from quantamind.types.settings import Settings


def test_a_refused_repository_is_never_cloned(tmp_path: Path, monkeypatch: Any) -> None:
    """A private repository on an account with no plan: refused BEFORE anything is fetched.

    The refusal is now decided by `serve/review/gate.py`, ahead of `deliver()`, so the ordering is
    asserted there. Billing is unconfigured, so the cached plan decides — and there is none.
    """
    root = tmp_path / "stores"
    root.mkdir()
    cloned: list[str] = []

    def _never(repo: str, *args: Any, **kwargs: Any) -> Path:
        cloned.append(repo)
        raise AssertionError(f"cloned {repo} before checking whether we would review it")

    monkeypatch.setattr(review_delivery, "ensure", _never)

    done = gate.review_pull_request(
        Review("acme/secret", 7, "deadbeef", author_id="1", author_login="alice", private=True),
        Settings(database_path=str(root), clone_root=str(tmp_path / "clones")),
    )

    assert cloned == [], "a repository we refused was cloned anyway"
    assert done.outcome is Outcome.NOT_ENTITLED
    assert "private repositories are on a paid plan" in (done.body or "")
