"""What the model is shown, read out of a REAL git repository built for each case.

WHAT: Builds an actual repository with two changed files, and asserts that `diff_for` returns the
      diff of the paths asked for and NOT the other file's, that an empty path list returns the
      empty string, and that a `git show` which exits non-zero raises rather than returning "".
WHY:  **THE EMPTY STRING IS THE DANGEROUS RETURN HERE.** `deep()` reads `if not text.strip()` as
      "those paths carry no diff" and reports `consulted=False` — a truthful "we did not ask".
      If a FAILED `git show` also returned "", an outage would be recorded as a change with
      nothing in it, and the difference between "no diff" and "we could not read the diff" is the
      distinction this product exists to keep (rule 3, silence must be typed).

      **THE SCOPE RESTRICTION IS THE THESIS, SO IT IS ASSERTED ON REAL OUTPUT.** The claim is that
      inference goes only where the ranker pointed; a diff that quietly carried the unranked file
      would mean the model reads the whole change while we bill and describe it as targeted.
      Nothing mocked: a real `git show` against a real object store.
IMPORTS: quantamind.serve.review.deep_prompt, quantamind.infer.vertex; stdlib subprocess,
      pathlib, pytest.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quantamind.infer import vertex
from quantamind.serve.review.deep_prompt import diff_for

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    "HOME": "/tmp",
}


def _run(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        env=GIT_ENV,
        timeout=30,
    )
    assert done.returncode == 0, f"git {' '.join(args)} failed: {done.stderr}"
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """A repository whose head commit changes `ranked.py` and `unranked.py`."""
    _run(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "ranked.py").write_text("x = 1\n")
    (tmp_path / "unranked.py").write_text("y = 1\n")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-q", "-m", "first")
    (tmp_path / "ranked.py").write_text("x = 2  # RANKED_MARKER\n")
    (tmp_path / "unranked.py").write_text("y = 2  # UNRANKED_MARKER\n")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-q", "-m", "second")
    return tmp_path, _run(tmp_path, "rev-parse", "HEAD")


def test_shows_only_the_ranked_file(repo: tuple[Path, str]) -> None:
    clone, sha = repo
    text = diff_for(clone, sha, ["ranked.py"])
    assert "RANKED_MARKER" in text
    assert "UNRANKED_MARKER" not in text, "the model was shown a file the ranker did not fund"


def test_no_paths_is_the_empty_string(repo: tuple[Path, str]) -> None:
    clone, sha = repo
    assert diff_for(clone, sha, []) == ""


def test_a_path_that_did_not_change_is_the_empty_string(repo: tuple[Path, str]) -> None:
    clone, sha = repo
    (clone / "untouched.py").write_text("z = 1\n")
    assert diff_for(clone, sha, ["untouched.py"]).strip() == ""


def test_a_failed_git_show_raises_rather_than_reading_as_no_diff(tmp_path: Path) -> None:
    """**THE ONE THAT MATTERS.** A directory that is not a repository must not look empty."""
    with pytest.raises(vertex.InferenceFailed) as caught:
        diff_for(tmp_path, "deadbeefdeadbeef", ["ranked.py"])
    assert "deadbeefdead" in str(caught.value), "the failure must name the commit it was reading"
