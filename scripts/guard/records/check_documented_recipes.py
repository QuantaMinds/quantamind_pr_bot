"""A documented `just` recipe or `quantamind` subcommand must exist, or be marked unbuilt.

WHAT: Scans the documentation for `just <recipe>` and `quantamind <subcommand>` and checks each
      one against reality -- the recipe names in the justfile, and the subparsers registered in
      `serve/arguments.py`. A subcommand the CLI itself lists as unbuilt must carry
      `documented-command:unbuilt` on the documenting line.
WHY:  `check_documented_commands.py` matches `python -m` and nothing else, so two whole classes of
      documented command were invisible to it. **`just fixtures` exited 1 on every invocation it
      ever had** -- it ran `git submodule update --init tests/fixtures/repos` against a repository
      with no `.gitmodules` and no submodules registered -- and CONTRIBUTING.md described it as
      working. Nobody noticed, because the only reader who would have run it was told it was not
      needed yet. That is the same failure the sibling guard was written for, arriving through the
      door it does not watch.

      SPLIT RATHER THAN EXTENDED. The sibling is 192 lines against a 200-line cap, and this needs
      a justfile parser and an AST read of the CLI. Both guards answer to the rule "a documented
      command must run" and the enforcement map names both.

      THE CLI'S OWN `UNBUILT` DICT IS THE SOURCE OF TRUTH, read from the AST rather than
      duplicated here. A list of unbuilt commands maintained in a guard would go stale the moment
      one was built, and would then demand the marker on a command that works.
IMPORTS: scripts/guard/discovery.py; stdlib ast, re. No project imports.
CONSUMED BY: `just guards`; CI.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

# Running a guard as a script puts only ITS directory on sys.path[0]. This one lives one level
# down, so the parent is added explicitly -- the same reason its sibling does it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from coverage import assert_examined, guarded, refuse_path_argument
from discovery import Violation, project_root, report

from records.declared_commands import cli_commands, recipes

# **A FLOOR, NOT A TARGET.** Below today's count, to catch discovery collapsing.
RECIPE_FLOOR = 20

DOC_ROOTS = (
    "docs/findings",
    "docs/engineering/CODEBASE.md",
    "docs/engineering/CLI.md",
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "BRIEFING.md",
)
UNBUILT = "documented-command:unbuilt"

# `just <recipe>`, and `quantamind <subcommand>` however it is invoked -- bare or after `uv run`.
JUST_CALL = re.compile(r"\bjust\s+(?P<recipe>[a-z][a-z0-9-]*)")
QM_CALL = re.compile(r"\bquantamind\s+(?P<command>[a-z][a-z0-9-]*)")
# A recipe definition: a name at column 0, optional parameters, then a colon.
# Only CODE is scanned: a fenced block, or a backtick span. Prose says "just falsified the
# hypothesis" and means the adverb. The alternative -- a blocklist of English words -- is a
# blocklist that goes stale silently, which is the defect class this guard exists to catch.
FENCE = re.compile(r"^\s*```")
BACKTICKED = re.compile(r"`([^`]+)`")


def _finds(pattern: re.Pattern[str], spans: Sequence[str]) -> Iterator[re.Match[str]]:
    """Matches inside EACH span separately, never across the gap between two of them.

    The first version joined the spans with a space and scanned once, which SYNTHESISED commands
    that no span contained. A sentence mentioning `quantamind` and `just` and
    `docs/engineering/CLI.md` became "quantamind just docs/engineering/CLI.md", out of which this
    guard read a subcommand `quantamind just` and a recipe `just docs` -- two invocations nobody
    had written, both reported as violations against correct prose.

    It failed loudly, which is the right direction for a guard to fail in, but it fails on text
    that is fine: any line with two adjacent code spans can manufacture a phantom command. The
    join was never needed -- a command lives inside ONE span or it is not a command.
    """
    for span in spans:
        yield from pattern.finditer(span)


def _documents(root: Path) -> list[Path]:
    found: list[Path] = []
    for entry in DOC_ROOTS:
        target = root / entry
        if target.is_file():
            found.append(target)
        elif target.is_dir():
            found.extend(sorted(target.rglob("*.md")))
    return found


def _stale(document: Path, number: int, invocations: list[str]) -> Violation:
    """A `documented-command:unbuilt` marker on something that now exists.

    **THE MARKER WAS A ONE-WAY SUPPRESSION WITH NO EXPIRY**, and that is what let `README.md` and
    `docs/engineering/CLI.md` carry "`quantamind review` — NOT BUILT" for months after it shipped.
    `if UNBUILT in line` ran before any check, so the guard could not tell a marker that is still
    true from one nobody removed -- it printed the same count either way. `qm-review-command.md`
    listed removing this marker under "Done when" and it was removed from `AGENTS.md` only.
    """
    named = ", ".join(f"`{x}`" for x in invocations)
    return Violation(
        document,
        number,
        "documented-recipe",
        f"this line carries {UNBUILT}, and everything it suppresses now exists: {named}. The "
        f"marker is stale: delete it, and correct any prose beside it still calling these "
        f"unbuilt. A marker nobody removes is how a shipped command stays documented as absent.",
    )


def main() -> int:
    root = project_root()
    known = recipes(root)
    commands, unbuilt = cli_commands(root)
    violations: list[Violation] = []
    suppressed = checked = 0

    for document in _documents(root):
        fenced = False
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                fenced = not fenced
                continue
            spans = [line] if fenced else BACKTICKED.findall(line)
            # **THE MARKER IS LINE-SCOPED, SO THE VERDICT MUST BE TOO.** `CODEBASE.md` carries
            # "Run `just check`. There is no `just docs-sync`" with one marker covering both: the
            # marker is doing real work for `docs-sync` and would read as stale for `check`. It is
            # stale only when EVERY invocation the line suppresses now exists.
            marked: list[tuple[str, bool]] = []
            for match in _finds(JUST_CALL, spans):
                name = match.group("recipe")
                checked += 1
                if UNBUILT in line:
                    suppressed += 1
                    marked.append((f"just {name}", name in known))
                elif name not in known:
                    violations.append(
                        Violation(
                            document,
                            number,
                            "documented-recipe",
                            f"`just {name}` names no recipe in the justfile",
                        )
                    )
            for match in _finds(QM_CALL, spans):
                name = match.group("command")
                checked += 1
                if UNBUILT in line:
                    suppressed += 1
                    marked.append((f"quantamind {name}", name in commands and name not in unbuilt))
                elif name not in commands:
                    violations.append(
                        Violation(
                            document,
                            number,
                            "documented-recipe",
                            f"`quantamind {name}` is not a registered subcommand",
                        )
                    )
                elif name in unbuilt:
                    violations.append(
                        Violation(
                            document,
                            number,
                            "documented-recipe",
                            f"`quantamind {name}` is listed UNBUILT in serve/arguments.py "
                            f"and exits 2 — "
                            f"document it as not built, or mark it {UNBUILT}",
                        )
                    )
            if marked and all(exists for _, exists in marked):
                violations.append(_stale(document, number, [n for n, _ in marked]))

    assert_examined("documented invocations", checked, RECIPE_FLOOR, root)
    print(f"[documented-recipes] {checked} documented invocation(s) checked", flush=True)
    if suppressed:
        print(f"[documented-recipes] {suppressed} documented command(s) NOT BUILT", flush=True)
    return report(violations, root, "documented-recipes")


if __name__ == "__main__":
    # Refused HERE, not inside main(): inside, `sys.argv` belongs to whoever
    # imported this module -- under pytest that is pytest's own command line.
    sys.exit(refuse_path_argument(sys.argv, "documented-recipes") or guarded(lambda: main()))
