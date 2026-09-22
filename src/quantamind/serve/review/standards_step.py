"""Apply the repository's declared standards to one change, and post the resulting status.

WHAT: `applied(clone, sha, paths, store, repo, number, settings)` returns `(checks, judged)` and
      posts the commit status. One call, both halves, exactly one status.
WHY:  **THE JUDGE IS CONSTRUCTED HERE AND INJECTED, NEVER REACHED FOR INSIDE `verify/`.**
      `AGENTS.md` rule 7 claimed the layer order stopped `verify` importing `infer` and it did not,
      because `infer` sits to the LEFT and the import runs leftward.
      `scripts/guard/check_conventions.py:FORBIDDEN` refuses that pair by name now. This module
      supplies the judge as a parameter, the way `verify/consumers.py` is given its clone.

      **THE STATUS IS COMPUTED FROM `checks` ALONE.** A model's verdict never moves a commit status:
      a status blocks a merge, and blocking on a claim measured 66.7-82.1% wrong would make the
      product an obstacle rather than a check. `judged` travels to the comment and stops.

      **SPLIT OUT OF `serve/review_delivery.py` FOR THE 200-LINE CAP, AND IT IS A REAL SEAM.**
      `deliver()` orchestrates: clone, rank, review, render, post. "Enforce the customer's declared
      standards" is one step of that with its own inputs and its own output, and it was the only
      step whose model wiring lived inline.
IMPORTS: ingest.publish.check_run, ingest.standards.{inherited,rules_file},
      serve.{blocking_status,rule_judge},
      types.{settings,standards.checked,standards.judged}, verify.rule_check. Leftward and
      sideways from `serve/`.
CONSUMED BY: `serve/review_delivery.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from quantamind.ingest.publish import check_run
from quantamind.ingest.standards import rules_file
from quantamind.ingest.standards.inherited import ORG_REPO, Inheritance, combine
from quantamind.serve.blocking_status import announce
from quantamind.serve.rule_judge import judge_with
from quantamind.types.admission.model_route import ModelRoute
from quantamind.types.settings import Settings
from quantamind.types.standards.checked import Checked
from quantamind.types.standards.judged import Judged
from quantamind.verify.rule_check import enforce

OrgClone = Callable[[str], Path | None]
"""Opens `<owner>/.quantamind`, or returns None when it cannot. **None is the common answer.**

Most installations have no organisation repository, and most that do will not have granted us
access to it. Injected so this step can be tested without a network call."""


def inheritance(repo: str, clone_org: OrgClone | None) -> Inheritance:
    """The organisation's rules for `repo`'s owner, or an empty readable inheritance.

    **NO ORGANISATION REPOSITORY IS NOT A FAILURE**, and is the default: `combine` is called with an
    empty organisation and `org_read` True, so the repository's own file stands as the whole
    standard. A repository we could not READ is the other case, and it sets `org_read` False.
    """
    if clone_org is None:
        return Inheritance(org_read=True)
    owner = repo.split("/")[0]
    opened = clone_org(f"{owner}/{ORG_REPO}")
    if opened is None:
        return Inheritance(org_read=False)
    org_rules, _ = rules_file.read(opened)
    return Inheritance(org_rules, org_read=True)


def applied(
    clone: Path,
    sha: str,
    paths: Sequence[str],
    store: Path,
    repo: str,
    number: int,
    settings: Settings,
    clone_org: OrgClone | None = None,
    route: ModelRoute | None = None,
) -> tuple[tuple[Checked, ...], tuple[Judged, ...], Inheritance]:
    """Run every declared standard over the change, post the status, return all three parts.

    The third is the D1e record: what was inherited, tightened, dropped or refused. **A drop that
    reached the rules without reaching the report would be the failure D1e exists to prevent.**
    """
    from_org = inheritance(repo, clone_org)
    own, _ = rules_file.read(clone, sha)
    merged = combine(
        from_org.rules,
        own,
        org_read=from_org.org_read,
        own_raw=list(rules_file.entries(clone, sha)),
    )
    checks, judged = enforce(
        clone,
        sha,
        list(paths),
        store,
        repo,
        number,
        judge_with(settings, route),
        inherited=merged.rules if clone_org is not None else None,
    )
    # **`checks` ONLY.** See the module docstring: a model verdict does not block a merge.
    announce(repo, sha, checks, enabled=settings.posting_enabled)
    # **C2: THE SAME PARSER ROWS, AT THE LINE.** A status says pass or fail; a check run puts each
    # violation on the diff where the developer is already looking. `judged` is deliberately NOT
    # passed — an annotation reads as a fact against a line, and a model verdict is not one.
    said = check_run.publish(repo, sha, checks, merged.rules, enabled=settings.posting_enabled)
    print(f"[checks] {said}", flush=True)
    return checks, judged, merged
