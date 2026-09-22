"""What the project actually provides: justfile recipes, and the CLI's registered subcommands.

WHAT: `recipes(root)` reads the justfile; `cli_commands(root)` parses `serve/arguments.py` and
      returns (every registered subcommand, the ones the CLI itself calls unbuilt).
WHY:  **Split from `check_documented_recipes.py` at the 200-line cap, on the seam between what
      EXISTS and what a document CLAIMS.** That guard was at 199 lines, so the marker-expiry rule
      in issue #96 could not be added without a split, and this is the honest one: everything here
      answers "what does this repository provide", and everything left there answers "does the
      prose agree".

      **THE UNBUILT SET IS READ FROM `serve/arguments.py`, NEVER LISTED HERE.** A list of unbuilt
      maintained inside a guard goes stale the moment one ships -- which is the exact defect the
      marker-expiry rule exists to catch, and it would be absurd to reintroduce it in the guard
      that catches it. The CLI registering a command is the fact; this reads it.
IMPORTS: stdlib ast and pathlib. No project imports, and none from `discovery` -- this module
      decides nothing and constructs no `Violation`.
CONSUMED BY: `scripts/guard/records/check_documented_recipes.py`.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

CLI = "src/quantamind/serve/arguments.py"
"""**THE PARSER, NOT THE DISPATCH.** `build_parser` and `UNBUILT` lived in `serve/cli.py` until
that file hit the 200-line cap and was split. This guard reads `add_parser` calls out of the AST,
so after the split `cli.py` held none and every documented command was reported unregistered --
the whole documentation gate inverted by a file move. It failed loudly, which is the only reason
this line is right rather than silently empty; see `_source` below for why."""

# A justfile recipe head: `name:` or `name arg="x":`, at the start of a line.
RECIPE_DEF = re.compile(r"^([a-z][a-z0-9-]*)\s*(?:[A-Za-z0-9_= \"'.]*)?:", re.MULTILINE)


def recipes(root: Path) -> set[str]:
    """Every recipe name the justfile defines. An absent justfile yields none, not an error."""
    justfile = root / "justfile"
    return (
        set(RECIPE_DEF.findall(justfile.read_text(encoding="utf-8")))
        if justfile.is_file()
        else set()
    )


class ParserMoved(RuntimeError):
    """`CLI` does not name a file. **RAISED, BECAUSE THE FALLBACK WAS AN EMPTY SET.**

    This function used to return `set(), set()` when the path was missing, and an empty set of
    registered commands makes every documented one look unregistered while a renamed or moved
    parser makes nothing fail at all -- the two outcomes are a flood and a silence, and neither
    says "the guard lost its subject". A clean zero here is a broken read until shown otherwise.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"{CLI} does not exist at {path}. The CLI's parser has moved or been renamed; "
            f"point `declared_commands.CLI` at its new home. Refusing to report zero registered "
            f"subcommands, which would pass every 'is this documented' check by having no subject."
        )
        self.path = path


def _source(root: Path) -> str:
    """The parser module's text. **Absent is an error, never an empty string.**"""
    path = root / CLI
    if not path.is_file():
        raise ParserMoved(path)
    return path.read_text(encoding="utf-8")


def cli_commands(root: Path) -> tuple[set[str], set[str]]:
    """(every registered subcommand, the ones the CLI itself calls unbuilt)."""
    tree = ast.parse(_source(root), filename=CLI)
    registered: set[str] = set()
    unbuilt: set[str] = set()
    for node in ast.walk(tree):
        # subparsers.add_parser("config", ...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            registered.add(node.args[0].value)
        # UNBUILT: dict[str, str] = {"review": "...", ...}
        if isinstance(node, ast.AnnAssign | ast.Assign):
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
            if isinstance(target, ast.Name) and target.id == "UNBUILT":
                value = node.value
                if isinstance(value, ast.Dict):
                    for key in value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            unbuilt.add(key.value)
    return registered | unbuilt, unbuilt
