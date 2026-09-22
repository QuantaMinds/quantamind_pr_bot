"""One pull request, end to end: admit it, refuse or review it, and settle what it cost.

WHAT: `review_pull_request(review, settings)` asks `admission.admit`, then either posts the refusal,
      runs the free (deterministic) review, or runs the full one — and on EVERY way out tells
      billing whether a reserved credit was consumed or must be refunded.
WHY:  **THE SETTLEMENT IS IN A `try`, BECAUSE EVERY EXIT MUST SETTLE.** A reservation taken before
      the clone and never closed charges the customer for a review that crashed. So an exception
      settles as `failed` before it propagates, and each quiet outcome settles by what it was.

      **FREE MEANS NO MODEL, ENFORCED BY SETTINGS RATHER THAN BY A FLAG EVERY STEP MUST HONOUR.**
      The free review runs the same pipeline with inference switched off, so no step can forget to
      check — the deep read, the summary and the rule judge all already obey `inference_enabled`.

      **A FAILED REVIEW THAT GITHUB REDELIVERS RUNS FREE.** Its credit was refunded, and billing
      allows one debit per commit, so the retry finds the reservation already made. That errs in
      the customer's favour, by one review, and only after a crash.

      **A REFUND KEEPS THE CUSTOMER WHOLE WHEN NOTHING REACHED THEM.** Nothing to say, a duplicate,
      or a model that never answered are all refunded; only a posted (or, with posting off,
      rehearsed) review that consulted the model is `consumed`.
IMPORTS: render.not_entitled, serve.review.{admission,refusal,review_delivery},
      types.{admission,forge.delivery,review,settings}. Same layer and leftward.
CONSUMED BY: `serve/commands/run_endpoint.py`.
"""

from __future__ import annotations

from dataclasses import replace

from quantamind.render.not_entitled import seat_footer
from quantamind.serve.review.admission import admit, settle
from quantamind.serve.review.refusal import refuse
from quantamind.serve.review.review_delivery import deliver
from quantamind.types.admission.decision import Mode
from quantamind.types.forge.delivery import Review
from quantamind.types.review import Delivered, Outcome
from quantamind.types.settings import Settings

QUIET = {Outcome.NOTHING_TO_SAY, Outcome.NO_READABLE_FILES, Outcome.NO_FILES}


def settlement(done: Delivered) -> str:
    """What happened to a reserved credit, from the outcome. Only a review that reached someone
    and consulted the model keeps its charge."""
    if done.outcome is Outcome.DUPLICATE:
        return "duplicate"
    if done.outcome in QUIET:
        return "nothing_posted"
    if not done.consulted:
        return "not_consulted"
    return "consumed"


def review_pull_request(review: Review, settings: Settings) -> Delivered:
    """Admit, then refuse or review, then settle. Never leaves a reservation open."""
    admission = admit(review, settings)
    if admission.mode is Mode.REFUSED:
        return refuse(review, admission, settings)

    if admission.unmetered:
        print(
            f"[serve] {review.repo}#{review.number}: UNMETERED — billing did not answer, so this "
            "paid account is reviewed free of charge",
            flush=True,
        )
    run_with = (
        settings if admission.mode is Mode.FULL else replace(settings, inference_enabled=False)
    )
    footer = seat_footer(admission) if admission.reason == "seat_full_public" else ""
    try:
        done = deliver(review.repo, review.number, review.head_sha, run_with, footer)
    except BaseException:
        settle(admission, settings, "failed")
        raise
    settle(admission, settings, settlement(done))
    return done
