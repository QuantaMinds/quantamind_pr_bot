"""The join: a verified delivery becomes a clone, a ranking, and a comment on the pull request.

WHAT: `deliver(repo, number, head_sha, settings)` clones or fetches the repository, asks GitHub
      what the pull request changed and what it was opened against, runs the ranking, and posts
      the comment -- or, with posting off, prints exactly what it would have posted. Returns a
      `Delivered` naming which outcome occurred.
WHY:  **THE ENDPOINT AUTHENTICATED DELIVERIES AND REVIEWED NOTHING.** `run_endpoint.work()` logged
      "NOT REVIEWED: no pipeline is attached to this callback" and returned. Every piece existed --
      `review()` ranks and renders, `changed_files()` and `base_commit()` read the pull request,
      `github_comments.post()` writes idempotently keyed on the head SHA -- and nothing joined
      them. This is that join, and it is the gap between a command-line tool and a product a
      customer can install.

      **POSTING IS OFF UNLESS TURNED ON, AND THE DRY RUN IS A COMPLETE REHEARSAL.** With
      `posting_enabled` false everything runs -- clone, fetch, API reads, ranking, rendering -- and
      the comment is printed instead of sent. So the thing being rehearsed is the delivery rather
      than a description of it, and the only step not exercised is the one that writes to someone
      else's project.

      **EVERY OUTCOME IS NAMED, INCLUDING THE QUIET ONES.** "Nothing worth saying", "every changed
      file is in a language we do not read", and "already commented on this commit" are three
      different results and a caller must be able to tell them apart. Collapsing them into a
      silent return is the defect this product exists to refuse -- `Outcome` is an enum for that
      reason, and mypy's exhaustiveness check is what keeps a seventh case from being forgotten.

      **THE BASE COMMIT'S TIMESTAMP BOUNDS THE HISTORY, AND IT IS NOT `now`.** A ranking that reads
      commits made after the pull request opened is scoring the change against its own future.
IMPORTS: ingest.{diff,github_api,github_comments}, serve.{commands.run_review,working_clone},
      types.settings.
      Rightmost layer.
CONSUMED BY: `serve/review/gate.py`, which decides BEFORE this runs whether the pull request may
      be reviewed and how fully — this function no longer reads the installation or the seat.
"""

from __future__ import annotations

from pathlib import Path

from quantamind.allocate.depth import plan as allocate
from quantamind.infer.change_review import explain
from quantamind.ingest.diff import base_commit, changed_files
from quantamind.ingest.github_api import token_for
from quantamind.ingest.publish.github_reviews import publish
from quantamind.serve.commands.run_review import review as run_ranking
from quantamind.serve.review.change_facts import gather
from quantamind.serve.review.deep_review import examine
from quantamind.serve.review.pin_review import only as only_pins
from quantamind.serve.review.pin_review import pins_for
from quantamind.serve.review.review_body import body_for
from quantamind.serve.review.standards_step import applied
from quantamind.serve.working_clone import ensure, sweep
from quantamind.store import tenancy
from quantamind.store.reviews import bank
from quantamind.types.change import REVIEWABLE_SUFFIXES
from quantamind.types.review import Delivered, Outcome
from quantamind.types.settings import Settings
from quantamind.types.spend import Spend


def deliver(
    delivery_repo: str, number: int, head_sha: str, settings: Settings, footer: str = ""
) -> Delivered:
    """Run the pipeline for one pull request and post, or rehearse posting.

    Takes the three fields rather than the `Review` record so this never imports the webhook
    parser: the join has no business knowing what shape GitHub's payload arrives in.
    """
    # **THE CLONE MUST AUTHENTICATE, BECAUSE EVERY CUSTOMER REPOSITORY IS PRIVATE.** That is
    # what a code reviewer is for. Without a credential git asks a terminal for a username and
    # exits 128, which is exactly what the first genuine `pull_request` delivery did -- after
    # every test passed, because a developer's machine has a credential helper and a container
    # does not. The token is minted only when an App is configured: an endpoint without one can
    # still read public repositories, and `token_for` would refuse rather than return nothing.
    app = bool(settings.app_id and settings.app_key_path)
    clone = ensure(
        delivery_repo,
        Path(settings.clone_root),
        token=token_for(delivery_repo) if app else None,
    )
    # **BOUND THE ROOT ON EVERY DELIVERY, AND PRINT THE COUNT RATHER THAN ASSUME IT.** `sweep()`
    # was written with a docstring explaining why it returns a number instead of claiming a
    # cleanup happened -- and was then never called from anywhere, for the whole of its existence.
    # Eleven gigabytes of clones accumulated in a single working session and filled the disk.
    #
    # It runs AFTER `ensure()` deliberately: `sweep` keeps the most recently modified clones and
    # the one just fetched is the newest, so this delivery's own clone cannot be what it deletes.
    swept = sweep(Path(settings.clone_root))
    if swept:
        print(f"[deliver] removed {swept} stale clone(s)", flush=True)

    store = tenancy.store_for(Path(settings.database_path), *delivery_repo.split("/", 1))

    # **FETCHED ONCE, UNFILTERED, THEN FILTERED HERE.** The ranker must see only files we read;
    # `pin_check` must see the workflows, which the ranker's filter removes. Two calls would cost
    # a second page walk and could disagree if the pull request changed between them.
    every_file = changed_files(delivery_repo, number, suffixes=None)
    changed = [name for name in every_file if name.endswith(REVIEWABLE_SUFFIXES)]

    # Detected BEFORE the early return: a workflow-only change is the commonest shape carrying a
    # pin mismatch, and ordering these the other way made the detector unreachable on exactly it.
    pins = pins_for(clone, head_sha, every_file)
    if not changed:
        return only_pins(delivery_repo, number, head_sha, pins, enabled=settings.posting_enabled)

    # **The base commit, not the head and not the clock.** See the module docstring.
    base = base_commit(delivery_repo, number, clone)
    reviewed = run_ranking(
        clone,
        delivery_repo,
        changed,
        # **ONE STORE PER REPOSITORY, NOT ONE FOR EVERYBODY.** `database_path` is now the root
        # under which each tenant gets its own file: the schema already separated them logically,
        # but a shared file means a shared blast radius and a shared SQLite writer lock, and
        # offboarding a customer means hand-written cascades across five tables instead of `rm`.
        store,
        as_of=base.committed_at,
        # **Passed so the review is RECORDED.** Without these the ranking runs and leaves no row,
        # which is how `review` and `ranked_unit` sat in the schema with zero writers.
        pr_number=number,
        head_sha=head_sha,
    )

    # **THE DETERMINISTIC HALF RUNS FIRST, AND THE ORDER IS THE POINT.** `applied()` decides every
    # declared rule with a parser and POSTS THE BLOCKING STATUS, so the verdict that can stop a
    # merge no longer waits on an inference call that cannot change it. It depends on nothing the
    # model produces -- clone, sha, changed paths, store -- so the only thing the old order bought
    # was latency on the half we actually sell.
    #
    # **THIS ALSO MAKES THE DOCUMENTED PIPELINE TRUE.** `docs/product/HOW_IT_WORKS.md` and the
    # pitch deck both describe rules as step one and the model as step three. They described the
    # rendered comment's order, not this function's, and nothing failed when the two disagreed.
    checks, judged, inherited = applied(
        clone, head_sha, list(changed), store, delivery_repo, number, settings
    )

    # **THE ALLOCATION DECIDES WHERE INFERENCE GOES.** The measured claim -- top three by fix
    # history misses 1.21% against alphabetical's 3.12% -- is about which files to read FIRST,
    # and a budget is the only consumer that claim ever fitted.
    reading = allocate(reviewed.ranking, list(changed))
    examined = examine(clone, head_sha, reading, list(changed), settings)
    # **THE DETERMINISTIC HALF, GATHERED WHETHER OR NOT THE MODEL RAN**, and reproducible on the
    # same commit by anyone — which is why it may be asserted where a model finding may not.
    facts = gather(clone, delivery_repo, number, changed, head_sha, base.sha)
    # `run_review` renders a ranking-only body for the CLI, which has no pull request to read a
    # goal from. The ranking already holds each file's prior-fix count, so the summary reads the
    # same numbers rather than querying the store twice and risking two answers.
    past = {u.unit.site.path: int(u.score.value) for u in reviewed.ranking.units}
    told, unreadable = explain(
        clone, head_sha, delivery_repo, number, reading.paths, settings, history=past
    )

    parts = (part.spend for part in (told, examined) if part is not None)
    bank(store, delivery_repo, number, head_sha, Spend.total(*parts))
    # Whether a model answered: what decides if a reserved credit is kept (`serve/review/gate.py`).
    consulted = (examined is not None and examined.consulted) or told is not None

    if reviewed.body is None and not pins:
        quiet = Outcome.NO_READABLE_FILES if not reviewed.considered else Outcome.NOTHING_TO_SAY
        return Delivered(quiet, reviewed.considered, reviewed.skipped, None, consulted)

    kept = examined.anchored if examined is not None else ()
    spoken = body_for(
        reviewed.ranking,
        summary=told,
        findings=kept,
        checks=checks,
        judged=judged,
        blind=unreadable,
        facts=facts,
        inherited=inherited,
    )
    body = (spoken if spoken is not None else (reviewed.body or "")) + pins + footer

    if not settings.posting_enabled:
        return Delivered(Outcome.REHEARSED, reviewed.considered, reviewed.skipped, body, consulted)

    wrote = publish(delivery_repo, number, head_sha, body, kept)
    return Delivered(
        Outcome.POSTED if wrote else Outcome.DUPLICATE,
        reviewed.considered,
        reviewed.skipped,
        reviewed.body,
        consulted,
    )
