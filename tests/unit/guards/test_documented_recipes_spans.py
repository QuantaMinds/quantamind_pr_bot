"""The recipe guard must not read a command across the gap between two backtick spans.

WHAT: Runs `check_documented_recipes.main()` end to end over a fixture project -- a justfile with
      one recipe, a CLI with one registered subcommand, and a CONTRIBUTING.md -- and asserts on
      the exit code and the violations it prints.
WHY:  The guard scanned a line as `" ".join(BACKTICKED.findall(line))`, joining every code span
      before matching, so `quantamind` followed by `just` followed by `docs/engineering/CLI.md`
      produced the commands `quantamind just` and `just docs`. Neither appears in any span. It
      reported them against correct prose and cost a red build on a pointer sentence.

      **THESE TESTS GO THROUGH `main()`, NOT THROUGH THE HELPER THAT SPLITS THE SPANS.** An
      earlier draft exercised `_finds` with spans it built itself; restoring the join at the call
      site left it green, because the join is in `main()` and the test never went near it. It
      would have shipped as a regression test for a fault it could not see. The whole path --
      file on disk, line, spans, match, violation -- is what has to be covered, because the whole
      path is where the fault lived.

      The last test pins the OLD behaviour as a known answer: joining the spans DOES manufacture
      `just docs`. Reintroducing the join fails there with the reason attached.
IMPORTS: the guard under test, loaded from scripts/guard/records. Nothing from src/.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "guard" / "records"))

from check_documented_recipes import BACKTICKED, JUST_CALL, QM_CALL, main  # noqa: E402
from declared_commands import CLI  # noqa: E402

# The sentence that broke it: three spans, the middle two adjacent across ordinary prose.
POINTER = (
    "Every command -- `quantamind` and `just` alike -- is documented in "
    "`docs/engineering/CLI.md` with its syntax."
)


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prose: str) -> int:
    """Scan a one-document project whose justfile has `fixtures` and whose CLI has `config`."""
    (tmp_path / "justfile").write_text("fixtures:\n    echo pinned\n", encoding="utf-8")
    # **THE PATH COMES FROM THE GUARD, NOT FROM A COPY OF IT.** This fixture hard-coded
    # `serve/cli.py`; when the parser moved to `serve/arguments.py` the fixture kept writing a
    # file the guard no longer reads, and a guard with no subject reports nothing wrong.
    cli = tmp_path / CLI
    cli.parent.mkdir(parents=True)
    cli.write_text(
        'UNBUILT: dict[str, str] = {"serve": "not built"}\n'
        'sub.add_parser("config")\n'
        'sub.add_parser("serve")\n',
        encoding="utf-8",
    )
    (tmp_path / "CONTRIBUTING.md").write_text(prose, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return main()


def test_adjacent_spans_do_not_synthesise_a_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fault, end to end: correct prose must not produce a violation."""
    code = _run(tmp_path, monkeypatch, POINTER)
    output = capsys.readouterr().out

    assert code == 0, f"correct prose was reported as a violation:\n{output}"
    assert "just docs" not in output, "a recipe was read across the gap between two spans"
    assert "quantamind just" not in output, "a subcommand was read across the gap between spans"


def test_a_command_inside_one_span_is_still_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fix that stops the guard matching anything is not a fix."""
    code = _run(tmp_path, monkeypatch, "Run `just fixtures`, then `quantamind config`.\n")
    output = capsys.readouterr().out

    assert code == 0, output
    assert "2 documented invocation(s) checked" in output, output


def test_an_unknown_command_inside_one_span_is_still_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The guard's actual job, unchanged: a command that does not exist is a violation."""
    code = _run(tmp_path, monkeypatch, "Run `just nope` and `quantamind nope` first.\n")
    output = capsys.readouterr().out

    assert code == 1, output
    assert "`just nope` names no recipe" in output, output
    assert "`quantamind nope` is not a registered subcommand" in output, output


def test_joining_the_spans_is_what_produced_the_phantom() -> None:
    """Known answer for the OLD behaviour, so the join cannot come back unnoticed."""
    spans = BACKTICKED.findall(POINTER)
    assert len(spans) == 3, f"the fixture must have three spans to be meaningful, got {spans}"
    joined = " ".join(spans)

    recipe = JUST_CALL.search(joined)
    command = QM_CALL.search(joined)
    assert recipe is not None and recipe.group("recipe") == "docs", (
        f"joining no longer manufactures `just docs` from {joined!r}; if the spans or the "
        f"patterns changed, this test is no longer pinning the fault it was written for"
    )
    assert command is not None and command.group("command") == "just"


def test_a_marker_on_a_command_that_now_exists_is_reported_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**THE ROT ITSELF — issue #96.** `config` is registered, so the marker is doing nothing.

    `documented-command:unbuilt` was a one-way suppression with no expiry: `if UNBUILT in line`
    ran before any check, so the guard printed the same count whether the marker was still true
    or nobody had removed it. That is what let `README.md` carry "`quantamind review` — NOT BUILT"
    for months after the command shipped.
    """
    prose = "Run `quantamind config` to print settings. documented-command:unbuilt"
    assert _run(tmp_path, monkeypatch, prose) == 1
    out = capsys.readouterr().out
    assert "marker is stale" in out, f"a marker on a built command was suppressed: {out!r}"
    assert "quantamind config" in out, "the violation must name what it found built"


def test_a_marker_covering_one_built_and_one_absent_invocation_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """**THE FALSE POSITIVE THE FIRST DRAFT PRODUCED, PINNED.**

    `CODEBASE.md` really carries "Run `just check`. There is no `just docs-sync`" under one
    marker. The marker is doing real work for `docs-sync`; a per-invocation rule condemned
    `check` beside it. A marker is stale only when EVERYTHING on its line now exists.
    """
    prose = "Run `just fixtures`. There is no `just docs-sync`. documented-command:unbuilt"
    assert _run(tmp_path, monkeypatch, prose) == 0, (
        "a marker still needed by one invocation was reported stale for its neighbour"
    )
    assert "marker is stale" not in capsys.readouterr().out


def test_a_marker_on_a_subcommand_the_cli_itself_calls_unbuilt_is_still_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`serve` is in the fixture CLI's UNBUILT map, so its marker is legitimate and must stay."""
    prose = "Run `quantamind serve` to bind. documented-command:unbuilt"
    assert _run(tmp_path, monkeypatch, prose) == 0
    assert "marker is stale" not in capsys.readouterr().out


def test_a_project_with_no_parser_module_raises_rather_than_reporting_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**THE KNOWN-ANSWER TEST FOR THE GUARD LOSING ITS SUBJECT.**

    `cli_commands` used to return two empty sets when `CLI` named no file, and this is the
    sabotage that tells that apart from a genuine "nothing is wrong": move the parser, and with
    the old fallback every documented command is reported unregistered while a renamed one is
    never checked at all. Neither outcome says the guard read nothing. Now it raises by name.
    """
    from declared_commands import ParserMoved, cli_commands

    (tmp_path / "justfile").write_text("fixtures:\n    echo pinned\n", encoding="utf-8")

    with pytest.raises(ParserMoved, match="does not exist at"):
        cli_commands(tmp_path)
