"""`quantamind reconcile` — ask the forge what it still covers, and correct what we hold.

WHAT: Loads settings, walks every live account (or one named with `--account`), and withdraws the
      repositories the forge no longer lists. Prints a line per account and a total.
WHY:  **IT IS A COMMAND RATHER THAN A TIMER INSIDE THE ENDPOINT** for the reason `migrate` is: it
      changes stored entitlement, so it runs where somebody can read the output, and a scheduler
      invoking it is an operator's decision rather than a behaviour the process acquired by
      starting. `serve/listener.py` stays a socket.

      **IT EXITS NON-ZERO WHEN AN ACCOUNT COULD NOT BE ASKED, AND THAT IS NOT PEDANTRY.** A run
      that reached nothing and a run that confirmed everything both withdraw zero repositories and
      both print a total. On a schedule, the only difference a human ever sees is the exit code, so
      a silent failure here is a reconciliation that stops happening without anyone noticing —
      which is the same defect class the thing it reconciles exists to catch.
IMPORTS: ingest.installation_scope, serve.reconcile, types.settings. Rightmost layer.
CONSUMED BY: `serve/cli.py`.
"""

from __future__ import annotations

from quantamind.ingest.installation_scope import covers
from quantamind.serve.installation.reconcile import reconcile
from quantamind.types.settings import SettingsError, load


def run_reconcile(account: str = "") -> int:
    """Correct stored entitlement against the forge. 0 when every account was reached."""
    try:
        settings = load()
    except SettingsError as exc:
        print(f"configuration error: {exc}")
        return 1

    report = reconcile(settings, lambda probe: covers(probe, settings), account=account)
    print(report.render())
    if report.unasked:
        # Named rather than summarised: "could not ask" is the state an operator has to act on,
        # and it is the one a nightly log is most likely to scroll past.
        return 1
    return 0
