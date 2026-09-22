"""`quantamind email` parses, dispatches, and refuses an unconfigured key by name.

WHAT: Drives `serve/arguments.build_parser` for the `email` subcommand and
      `serve/commands/run_email.run_email` for the unconfigured-key path.
WHY:  **THE MISSING-KEY PATH IS THE ONE THAT HAS ACTUALLY SHIPPED BROKEN HERE.** Three secrets
      in `.env` were read by nothing and the endpoint reported them absent. The assertion is on
      the exit code AND on the variable name in the output, because a command that exits 2 with
      a message naming nothing leaves an operator guessing which of four keys is wrong.

      **THE KEY IS PASSED AS A MAPPING, NOT SET IN `os.environ`.** `credential(name, env)` takes
      one so a test configures it without leaking into whatever runs next.
IMPORTS: pytest, quantamind.serve.{arguments,commands.run_email}, quantamind.types.dotenv.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

from quantamind.ingest.notify.resend_api import KEY_VARIABLE
from quantamind.serve.arguments import build_parser
from quantamind.serve.commands.run_email import run_email
from quantamind.types.dotenv import credential


def test_the_subcommand_parses_with_only_a_recipient() -> None:
    """Everything but `--to` has a default, so proving the key takes one flag."""
    args = build_parser().parse_args(["email", "--to", "media@quantamind.co"])

    assert args.command == "email"
    assert args.to == ["media@quantamind.co"]
    assert args.sender == "onboarding@resend.dev"
    assert args.subject == "QuantaMind test"


def test_to_is_repeatable_and_from_is_overridable() -> None:
    args = build_parser().parse_args(
        ["email", "--to", "a@b.co", "--to", "c@d.co", "--from", "hello@quantamind.co"]
    )

    assert args.to == ["a@b.co", "c@d.co"]
    assert args.sender == "hello@quantamind.co"


def test_an_unconfigured_key_exits_two_and_names_the_variable(capsys) -> None:  # type: ignore[no-untyped-def]
    """**NOT EXIT 0 HAVING DONE NOTHING**, which is the failure AGENTS.md rule 15 is about.

    The empty mapping is the point: without it this test falls through to the real `.env`, sends
    a live message on every `just check`, and passes or fails depending on whose laptop it ran
    on. `capsys` is pytest's own capture fixture and is untyped upstream.
    """
    code = run_email(to=("media@quantamind.co",), sender="x@y.co", subject="s", html="h", env={})
    printed = capsys.readouterr().out

    assert code == 2
    assert KEY_VARIABLE in printed
    assert "Nothing was sent." in printed


def test_a_configured_but_blank_key_still_refuses_rather_than_attempting(capsys) -> None:  # type: ignore[no-untyped-def]
    """`RESEND_API_KEY=` — set but empty, which is what commenting a line out in a `.env`
    produces. It must refuse the same way an absent one does, not call Resend unauthenticated."""
    code = run_email(
        to=("media@quantamind.co",), sender="x@y.co", subject="s", html="h", env={KEY_VARIABLE: ""}
    )

    assert code == 2
    assert "Nothing was sent." in capsys.readouterr().out


def test_credential_reads_the_variable_from_the_mapping_it_is_given() -> None:
    """The name the command asks for is the name an operator writes. Read through one function."""
    assert credential(KEY_VARIABLE, {KEY_VARIABLE: "re_abc"}) == "re_abc"
    assert credential(KEY_VARIABLE, {}) == ""
