"""Every flag and subcommand `quantamind` accepts, and nothing about what they then do.

WHAT: `build_parser()` and `UNBUILT`, the commands registered so they exit non-zero naming the
      stage that delivers them rather than exiting 0 having done nothing.
WHY:  **SPLIT FROM `serve/cli.py` AT THE 200-LINE CAP, AND IT IS A REAL SEAM.** That file had
      reached exactly 200 lines, so `email` could not be added to it at all. What the CLI ACCEPTS
      and what the CLI DOES are two concerns: this half is read by anyone asking what the surface
      is, and `check_documented_recipes.py` reads `UNBUILT` from here to decide which commands the
      documentation is allowed to call unbuilt. The other half is a dispatch table.

      **THE UNBUILT LIST LIVES IN ONE PLACE AND IS NOT RESTATED IN A DOCSTRING.** `cli.py` already
      carried that warning for the same reason: a list written twice is a list that disagrees with
      itself, and the copy nobody runs is the one a reader believes.
IMPORTS: stdlib (argparse, pathlib) and `quantamind.__version__`. Nothing from any layer, so
      `--help` and `--version` answer even when a layer below is broken.
CONSUMED BY: `serve/cli.py`, `scripts/guard/records/check_documented_recipes.py`, and tests/unit.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from quantamind import __version__

# Commands named in AGENTS.md that have no implementation behind them yet. They parse and
# exit non-zero with the stage that will deliver them, rather than exiting 0 having done
# nothing -- a documented command that silently succeeds is how a runbook comes to report
# work it never did.
UNBUILT: dict[str, str] = {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quantamind",
        description="A code reviewer that reports what it did not check.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("config", help="print the resolved configuration and exit")
    subparsers.add_parser("migrate", help="bring an existing store up to this build's schema")
    mend = subparsers.add_parser(
        "reconcile", help="ask the forge what it still covers; withdraw what it no longer lists"
    )
    mend.add_argument("--account", default="", help="one account; default is every live one")
    show = subparsers.add_parser(
        "dashboard", help="what we commented on, whether it merged, what production said"
    )
    show.add_argument("repo", help="owner/name, as recorded")
    show.add_argument("--limit", type=int, default=100)
    # **D1d: PROPOSES, NEVER DECLARES.** The pull requests are named rather than crawled — this
    # product has never run a "recent changes" search and will not pretend to here.
    mined = subparsers.add_parser(
        "standards", help="what reviewers of these pull requests said more than once"
    )
    mined.add_argument("--repo", required=True, help="owner/name on GitHub")
    mined.add_argument(
        "--pulls", type=int, nargs="+", required=True, metavar="N", help="pull request numbers"
    )
    rules = subparsers.add_parser(
        "compliance", help="every declared rule and what happened to it, per repository"
    )
    rules.add_argument("--repo", required=True, help="owner/name as recorded in the store")
    # **AN ARTEFACT, NOT A QUERY.** D4b claimed "exportable" while only a summary could be read
    # out; a compliance team is handed a file, and the file carries its own limits.
    rules.add_argument(
        "--export",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the whole audit trail to PATH as JSON, with what it does not cover stated",
    )

    money = subparsers.add_parser(
        "cost", help="what this repository's reviews spent, from the rows that recorded it"
    )
    money.add_argument("--repo", required=True, help="owner/name as recorded in the store")

    listen = subparsers.add_parser(
        "serve", help="authenticate and de-duplicate GitHub webhooks over HTTP"
    )
    listen.add_argument("--port", type=int, default=7331)
    # **`--host` MUST BE ASKED FOR.** Loopback by default so a developer does not expose an
    # endpoint to their network by omission; the container passes 0.0.0.0 deliberately.
    listen.add_argument("--host", default="127.0.0.1", help="bind address; 0.0.0.0 in a container")
    look = subparsers.add_parser(
        "review", help="rank one change's files against history and print what we would say"
    )
    look.add_argument("clone", type=Path, help="a full clone; nothing is sent anywhere")
    look.add_argument("--repo", default="local/clone", help="owner/name, for the store key")
    look.add_argument(
        "--sha",
        default="",
        help="the commit to review. Omit it to review what you have NOT committed yet, or "
        "the commits on this branch that are not on the default one — which is the review "
        "worth having before you open a pull request",
    )
    # **SUPPRESSED FROM `--help`, NOT REMOVED, AND OFF UNLESS ASKED FOR BY NAME.**
    # `docs/product/QUANTAMIND.md` says the product publishes no model findings. A flag advertised
    # in `--help` contradicts that document, and a CLI quietly offering what the canonical document
    # says is not shipped is precisely the drift this project spends its time catching.
    #
    # It stays because the measurement half needs it: raw findings are **66.7-82.1% wrong** at
    # **0.013-0.037 correct per pull request**, and the parser gate in front of it has adjudicated
    # exactly ONE live finding — which it dropped. That is not a capability to put in front of a
    # customer; it is an instrument for finding out whether it could ever be one.
    look.add_argument(
        "--json", action="store_true", dest="as_json", help="print the review as JSON for a tool"
    )
    look.add_argument("--deep", metavar="GCP_PROJECT", default="", help=argparse.SUPPRESS)
    first = subparsers.add_parser("scan", help="walk a clone's history; say where rework lands")
    first.add_argument("clone", type=Path, help="a full clone; nothing is sent unless asked")
    first.add_argument("--explain", metavar="GCP_PROJECT", default="", help=argparse.SUPPRESS)
    walk = subparsers.add_parser(
        "retrospective", help="replay the ranker over a clone's own history and report"
    )
    walk.add_argument(
        "clone", type=Path, nargs="+", help="one or more full clones; nothing is sent anywhere"
    )
    walk.add_argument("--repo", default="local/clone", help="owner/name, for the report heading")
    # **IT SENDS REAL MAIL AND THERE IS NO REHEARSAL FLAG, WHICH IS WHY EVERY FIELD IS TYPED
    # OUT.** `serve` has `POSTING_ENABLED` because it runs unattended against somebody else's
    # repository; this runs only when a person types it, addressed to whoever they name. A
    # `--dry-run` here would rehearse the one part that cannot fail quietly and skip the part
    # that can -- whether the key works and whether the sending domain is verified.
    mail = subparsers.add_parser(
        "email", help="send one email through Resend; proves the key and the sending domain work"
    )
    mail.add_argument("--to", required=True, action="append", metavar="ADDRESS", help="repeatable")
    # **`onboarding@resend.dev` DELIVERS ONLY TO THE ACCOUNT OWNER.** It is Resend's own sandbox
    # sender and needs no verified domain, so the default proves the key without also requiring
    # DNS to be right. Mail to anyone else needs `--from` on a domain verified in the account.
    mail.add_argument("--from", dest="sender", default="onboarding@resend.dev", metavar="ADDRESS")
    mail.add_argument(
        "--subject", default="QuantaMind test", help="blank is refused, not defaulted"
    )
    mail.add_argument("--html", default="<p>Sent by QuantaMind.</p>", help="the HTML body")
    for name, stage in UNBUILT.items():
        subparsers.add_parser(name, help=f"NOT BUILT — arrives with {stage}")
    return parser
