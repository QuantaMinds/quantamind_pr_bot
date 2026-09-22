"""The command line: the same pipeline, invoked locally, posting nothing.

WHAT: `main()`, which is one dispatch table. `config` prints the resolved settings,
      `retrospective` replays the ranker over a clone's own history, `serve` binds the webhook
      endpoint, `review` ranks one change from a clone and prints what we would say, `reconcile`
      asks the forge what an installation still covers, and `email` sends one message through
      Resend. **The surface itself -- every flag, and the list of
      commands that are registered but unbuilt -- moved to `serve/arguments.py`** when this file
      hit the 200-line cap and `email` could not be added to it.
WHY:  The CLI is not a convenience. It runs the retrospective, it is how a sceptic verifies
      us before granting repository access, and it is what answers the ranker gate. So it is
      built first and stays. The App is this plus a webhook, a signature check and
      idempotency -- and the pipeline must not know which one called it, or what a customer
      verified here is not what runs there.
IMPORTS: stdlib argparse and `serve.arguments` plus `types.settings` at module scope. Every
      command's implementation is imported INSIDE the branch that needs it, so `--version` and
      `config` still answer when a layer below is broken.
CONSUMED BY: the `quantamind` entry point in pyproject.toml, and tests/unit.
"""

from __future__ import annotations

from collections.abc import Sequence

from quantamind.serve.arguments import UNBUILT, build_parser
from quantamind.types.settings import SettingsError, load

__all__ = ["UNBUILT", "build_parser", "main"]
"""**`build_parser` AND `UNBUILT` STAY IMPORTABLE FROM HERE.** Tests and a guard already reach
for them at this name, and the question they answer -- what does the CLI accept -- did not change
because the definition moved file."""


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns an exit code rather than calling sys.exit, so tests can assert it."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command in UNBUILT:
        print(
            f"`quantamind {args.command}` is not built yet — it arrives with "
            f"{UNBUILT[args.command]}.\n"
            "See docs/plans/implementation.md for the stage and its gate."
        )
        return 2

    if args.command == "serve":
        from quantamind.serve.commands.run_endpoint import run

        return run(args.port, args.host)

    if args.command == "review":
        from quantamind.serve.commands.run_commit import review_commit

        return review_commit(
            args.clone, args.repo, args.sha, deep_project=args.deep, as_json=args.as_json
        )

    if args.command == "scan":
        from quantamind.serve.commands.run_scan import run_scan

        return run_scan(args.clone, explain=args.explain)

    if args.command == "retrospective":
        from quantamind.serve.commands.run_retrospective import run_retrospective

        return run_retrospective(args.clone, args.repo)

    if args.command == "migrate":
        from quantamind.serve.commands.run_migrate import run_migrate

        return run_migrate()

    if args.command == "reconcile":
        from quantamind.serve.commands.run_reconcile import run_reconcile

        return run_reconcile(args.account)

    if args.command == "standards":
        from quantamind.serve.commands.run_standards import run_standards

        return run_standards(args.repo, args.pulls)

    if args.command == "compliance":
        from quantamind.serve.commands.run_report import run_compliance

        return run_compliance(args.repo, args.export)

    if args.command == "cost":
        from quantamind.serve.commands.run_report import run_cost

        return run_cost(args.repo)

    if args.command == "email":
        from quantamind.serve.commands.run_email import run_email

        return run_email(
            to=tuple(args.to), sender=args.sender, subject=args.subject, html=args.html
        )

    if args.command == "dashboard":
        from quantamind.serve.commands.run_report import run_dashboard

        return run_dashboard(args.repo, args.limit)

    try:
        settings = load()
    except SettingsError as exc:
        print(f"configuration error: {exc}")
        return 1

    from quantamind.render.config import render_config

    print(render_config(settings))
    return 0
