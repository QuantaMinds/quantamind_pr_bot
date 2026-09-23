"""Tell a pull request it was not reviewed, and why — on the comment and on the required status.

WHAT: `refuse(review, admission, settings)` posts the refusal comment and a commit status, then
      returns the `Delivered` record. A removed installation posts nothing: we can no longer write.
WHY:  **THE STATUS IS `success` WITH A SENTENCE, NEVER AN ABSENT STATUS AND NEVER A FAILURE.**
      `main` requires `quantamind/declared-rules`; an absent status renders `pending` forever and
      deadlocks the merge (the defect #107 fixed for "nothing governed"). A failure would block a
      customer from merging their own code over our seat or credit rules, which no competitor does.
      So the state unblocks, and the description names exactly why no review happened — the same
      move `render/blocks/status_check.NOTHING_GOVERNED` makes.

      **A STATUS THAT CANNOT BE POSTED DOES NOT UNDO THE REFUSAL.** The comment is the message; the
      status is a courtesy to branch protection, and its failure is logged rather than raised.
IMPORTS: ingest.publish.{commit_status,github_reviews}, render.not_entitled, types.{admission,
      forge.delivery,review,settings}. Leftward only.
CONSUMED BY: `serve/review/gate.py`.
"""

from __future__ import annotations

from quantamind.ingest.publish import commit_status
from quantamind.ingest.publish.github_reviews import publish
from quantamind.render.not_entitled import refusal
from quantamind.types.admission.decision import Admission
from quantamind.types.forge.delivery import Review
from quantamind.types.review import Delivered, Outcome
from quantamind.types.settings import Settings

SHORT = {
    "private_needs_plan": "private repositories need a paid plan",
    "no_credits": "no review credits left this period",
    "byok_key_missing": "no Gemini API key is saved for this account",
}


def status_line(admission: Admission) -> str:
    """The required status's description: at most 140 characters, and always starting the same."""
    if admission.reason == "seat_full":
        why = f"@{admission.author_login or 'the author'} needs a QuantaMind seat"
    else:
        why = SHORT.get(admission.reason, admission.reason)
    return f"Not reviewed: {why}"[: commit_status.DESCRIPTION_LIMIT]


def refuse(review: Review, admission: Admission, settings: Settings) -> Delivered:
    """Post why this pull request was not reviewed. Nothing is read, cloned or charged."""
    if admission.reason == "removed":
        print(f"[serve] {review.repo}#{review.number}: App removed; nothing posted", flush=True)
        return Delivered(Outcome.NOT_ENTITLED, (), (), None)

    body = refusal(admission, settings.web_app_url)
    print(f"[serve] {review.repo}#{review.number}: not reviewed — {admission.reason}", flush=True)
    if settings.posting_enabled:
        publish(review.repo, review.number, review.head_sha, body, ())
        try:
            commit_status.post(review.repo, review.head_sha, "success", status_line(admission))
        except commit_status.StatusFailed as exc:
            print(f"[serve] {review.repo}#{review.number}: status not posted — {exc}", flush=True)
    return Delivered(Outcome.NOT_ENTITLED, (), (), body)
