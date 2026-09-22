"""`quantamind email` — read the key, send one message, print the id or the reason.

WHAT: `run_email(...)`. Returns an exit code rather than calling sys.exit, so a test can assert
      on it. Prints Resend's id on success and Resend's own sentence on failure.
WHY:  **THE COMMAND EXISTS SO THE CREDENTIAL IS PROVEN BY RUNNING SOMETHING, NOT BY READING IT.**
      Three secrets in `.env` were read by nothing -- `run_endpoint.py` took them from
      `os.environ` while `from_file` deliberately does not touch it, so a configured file
      produced *"no webhook secret: refusing to bind"*. A fourth key with no command behind it
      would be the same defect with a new name. This is that command, and it is the whole
      difference between a variable that is set and a variable that works.

      **A MISSING KEY NAMES THE VARIABLE AND EXITS 2, IT DOES NOT EXIT 0 HAVING DONE NOTHING.**
      `AGENTS.md` rule 15 exists because a documented command that ignores its flags, writes
      nothing and exits 0 let a runbook report work it never did.

      **WHAT IT PRINTS IS THE ID, AND THE SENTENCE UNDER IT SAYS WHY THAT IS NOT DELIVERY.**
      Resend returning 2xx means it accepted the message for sending. Whether it reached an inbox
      is an event this process never observes, and printing "sent" full stop would be this
      project's own named failure -- a check whose output is the same whether or not the thing
      it checks is working.
IMPORTS: `ingest.notify.resend_api`, `types.dotenv`, `types.deployment`. Rightmost layer.
CONSUMED BY: `serve/cli.py`.
"""

from __future__ import annotations

from collections.abc import Mapping

from quantamind.ingest.notify.resend_api import KEY_VARIABLE, EmailFailed, send
from quantamind.types.deployment import NetworkRefused
from quantamind.types.dotenv import credential


def run_email(
    *,
    to: tuple[str, ...],
    sender: str,
    subject: str,
    html: str,
    env: Mapping[str, str] | None = None,
) -> int:
    """Send one email. 0 when Resend accepted it, 2 when it did not.

    **`env` IS INJECTABLE SO THE UNCONFIGURED PATH IS TESTABLE WITHOUT SENDING MAIL.** A test
    that fell through to the real `.env` would post a live message every time somebody ran
    `just check`, and would pass or fail depending on whose laptop it ran on.
    """
    api_key = credential(KEY_VARIABLE, env)
    if not api_key:
        print(
            f"no Resend API key: {KEY_VARIABLE} is set in neither the environment nor the "
            f"repository `.env`. Nothing was sent."
        )
        return 2
    try:
        accepted = send(api_key=api_key, sender=sender, to=to, subject=subject, html=html)
    except NetworkRefused as refused:
        print(f"{refused}")
        return 2
    except EmailFailed as failed:
        print(f"Resend refused it: {failed.reason}\nNothing was sent.")
        return 2

    print(
        f"Resend accepted it.\n"
        f"  id:   {accepted.id}\n"
        f"  from: {sender}\n"
        f"  to:   {', '.join(accepted.to)}\n"
        f"Accepted is not delivered — this process never sees the inbox. Search that id in the "
        f"Resend dashboard for what happened after we handed it over."
    )
    return 0
