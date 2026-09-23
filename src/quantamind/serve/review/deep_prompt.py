"""The two texts the deep pass shows the model, read out of the clone.

WHAT: `diff_for(clone, sha, paths)` is the diff restricted to the ranked files;
      `context_for(clone, sha, changed)` is the shape of the WHOLE change as prompt text.
WHY:  **THE SCOPES DIFFER ON PURPOSE AND THAT IS THE THESIS.** The model reads only the files the
      ranker funded, while the shape it is told about is counted over every changed file -- "6
      files where your median is 2" is a fact about the change, and would be false if counted over
      the three we happened to pay for. Keeping both in one module is what stops the second from
      quietly being narrowed to the first.

      **A SHAPE THAT CANNOT BE MEASURED YIELDS NO CONTEXT, NEVER A GUESSED ONE.** `change_shape`
      raises rather than falling back to a wall-clock window, and the honest answer here is the
      empty string -- the prompt the model saw before any of this was measured.

      Split from `deep_review.py` when that file passed the 200-line cap: reading material out of
      a clone and running a model pass over it are two concerns, which is rule 6.
IMPORTS: infer.vertex (the failure type), ingest.{change_shape,review_window},
      render.blocks.shape_line. Rightmost layer, so all are allowed.
CONSUMED BY: `serve/review/deep_review.py`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from quantamind.infer import vertex
from quantamind.ingest.change_shape import shape
from quantamind.ingest.review_window import WindowUnreadable
from quantamind.render.blocks.shape_line import block

GIT_TIMEOUT_S = 60


def diff_for(clone: Path, sha: str, paths: list[str]) -> str:
    """The diff of `sha` restricted to `paths`. Empty when those files did not change."""
    if not paths:
        return ""
    done = subprocess.run(
        ["git", "-C", str(clone), "show", sha, "--", *paths],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_S,
    )
    if done.returncode != 0:
        raise vertex.InferenceFailed(
            f"git show {sha[:12]} exited {done.returncode}: {done.stderr.strip()[:120]}"
        )
    return done.stdout


def context_for(clone: Path, sha: str, changed: list[str]) -> str:
    """The change's shape as prompt text. Empty when git could not settle the commit's own time."""
    try:
        return block(shape(clone, sha, changed))
    except WindowUnreadable:
        return ""
