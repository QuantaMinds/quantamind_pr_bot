"""What a pull request is told when we are not going to review it, or review it only partly.

WHAT: `refusal(admission)` returns the comment for a refused pull request;
      `seat_footer(admission)` returns the line appended to a free review when the author has no
      seat.
WHY:  **A REFUSAL THAT POSTS NOTHING IS INDISTINGUISHABLE FROM A CLEAN REVIEW.** "We will not
      review this" and "we looked and found nothing" must not arrive as the same blank space.

      **EACH REASON SAYS ITS OWN TRUE THING.** The first version said "private repositories are on
      a paid plan" under EVERY refusal — including a removed installation and a repository with
      too few stars — so the one sentence a customer could act on was wrong most of the times it
      showed. Now the reason is billing's code, and each code has one sentence.

      **IT NAMES THE AUTHOR WHEN THE FIX IS ABOUT THEM**, as CodeRabbit does: a seat is a person,
      and "someone needs a seat" sends an admin hunting. It never names anyone for a reason that
      is about the account (no plan, no credits, no key).

      **NO VERDICT ON THE CODE APPEARS HERE**: a review that did not happen must never open with
      an opinion about code nobody read. It names the rule, never our mechanism.
IMPORTS: types.admission.decision.
CONSUMED BY: `serve/review/refusal.py`, `serve/review/gate.py`.
"""

from __future__ import annotations

from datetime import datetime

from quantamind.types.admission.decision import Admission

HEADER = "### QuantaMind"
PRICING = "https://quantamind.co/pricing"
ACCOUNT = "https://quantamind.co/account"
NOTHING_READ = (
    "Nothing below is a verdict on your code — there is nothing below, because nothing was read."
)


def _date(iso: str) -> str:
    """`2026-11-01T00:00:00.000Z` as "1 November 2026", or the raw value if it will not parse."""
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return iso
    return f"{when.day} {when:%B %Y}"


def _why(admission: Admission) -> str:
    author = f"@{admission.author_login}" if admission.author_login else "The author"
    reason = admission.reason
    if reason == "private_needs_plan":
        return (
            "This is a private repository, and private repositories are on a paid plan. The free "
            f"tier covers public repositories. Plans start with a 14-day trial — [see the plans]"
            f"({PRICING})."
        )
    if reason == "seat_full":
        return (
            f"{author} does not have a QuantaMind seat. This account's plan has "
            f"{admission.seats_included} seat(s) and all {admission.seats_used} are in use. An "
            f"admin can add a seat or free one at [quantamind.co/account]({ACCOUNT})."
        )
    if reason == "no_credits":
        reset = (
            f" The allowance resets on {_date(admission.resets_at)}." if admission.resets_at else ""
        )
        return (
            "This account has used all of its review credits for this period."
            f"{reset} An admin can buy more at [quantamind.co/account]({ACCOUNT})."
        )
    if reason == "byok_key_missing":
        return (
            "This account is on the bring-your-own-key plan, and no working Gemini API key is "
            f"saved. An admin can add one at [quantamind.co/account]({ACCOUNT})."
        )
    return f"This change could not be reviewed ({reason or 'no reason was given'})."


def refusal(admission: Admission) -> str:
    """The comment for a pull request we declined to review.

    **AN EMPTY REASON IS REFUSED.** A refusal that cannot say why is the silence this module
    exists to replace, wearing a comment's clothes.
    """
    if not admission.reason.strip():
        raise ValueError(
            "a refusal must carry its reason; an unexplained one is silence with a header"
        )
    return f"{HEADER}\n\n**This change was not reviewed.** {_why(admission)}\n\n{NOTHING_READ}"


def seat_footer(admission: Admission) -> str:
    """The line under a FREE review of a public repository whose author has no seat."""
    author = f"@{admission.author_login}" if admission.author_login else "The author"
    return (
        f"\n\n---\n_This is the free review. {author} does not have a QuantaMind seat "
        f"({admission.seats_used} of {admission.seats_included} in use), so the full review did "
        f"not run. An admin can add a seat at [quantamind.co/account]({ACCOUNT})._"
    )
