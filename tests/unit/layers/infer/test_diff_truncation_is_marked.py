"""Verification that a diff cut to fit the prompt says it was cut.

WHAT: Pins `infer/change_summary._capped` — the diff passes through untouched when it fits, and
      carries an explicit marker when it does not.
WHY:  **THE COMMENT BESIDE `MAX_DIFF_CHARS` CLAIMED THE TRUNCATION WAS "VISIBLE IN THE OUTPUT"
      AND NOTHING MADE IT SO.** The diff was sliced with `diff[:MAX_DIFF_CHARS]` and handed to
      the model, which then read a change that stopped mid-hunk with no way to know it had, and
      summarised it as though it were the whole thing. That is rule 14 exactly: a comment may
      explain why, never assert whether.

      **THE PATTERN WAS ALREADY IN THE CODEBASE.** `ingest/standards/conventions.py` marks its
      own truncation with the same kind of sentinel; the diff path simply never did.

      **AND THE CONSTANT WAS NEVER SWEPT.** `30_000` is written with a separator, and the
      mutation tool sliced by `len(repr(value))` — five characters against six — so it refused
      rather than mutating. Three constants were skipped that way and reported as neither caught
      nor surviving. Fixed in `scripts/measure/mutate.py`, and all four mutations survive.
IMPORTS: pytest, quantamind.infer.change_summary.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import pytest

from quantamind.infer import gemini, vertex
from quantamind.infer.change_summary import MAX_DIFF_CHARS
from quantamind.infer.diff_cap import TRUNCATED, capped

CAP = 30_000
"""The shipped cap, written out. `MAX_DIFF_CHARS + 1` would read the value under test."""


def test_the_cap_is_thirty_thousand_characters() -> None:
    """Cut from 60,000 when a real 27-file delivery hit MAX_TOKENS."""
    assert MAX_DIFF_CHARS == CAP


def test_a_diff_that_fits_is_passed_through_untouched() -> None:
    """No marker on an intact diff: a reader must not think something was hidden."""
    diff = "+ added a line\n" * 10

    assert capped(diff, CAP) == diff
    assert TRUNCATED not in capped(diff, CAP)


def test_a_diff_at_exactly_the_cap_is_not_marked() -> None:
    """The boundary. Marking an intact diff would be a false warning."""
    assert capped("x" * CAP, CAP) == "x" * CAP


def test_a_longer_diff_is_cut_and_says_so() -> None:
    """The failure being fixed: the model must be able to tell it was not shown everything."""
    cut = capped("x" * (CAP + 5_000), CAP)

    assert cut.startswith("x" * CAP)
    assert cut.endswith(TRUNCATED)
    assert "truncated" in TRUNCATED, "the marker no longer says what happened"


def test_the_kept_portion_is_the_beginning_of_the_diff() -> None:
    """Keeping the tail would drop the files a reviewer reads first."""
    diff = "FIRST-HUNK\n" + "y" * (CAP * 2)

    cut = capped(diff, CAP)

    assert cut[: len("FIRST-HUNK")] == "FIRST-HUNK"
    assert len(cut) == CAP + len(TRUNCATED)


# --- the review prompt uses the same rule with its own, larger limit ----------------------------
#
# **`gemini.py` SLICED ITS DIFF THE SAME WAY AND WAS THE LAST ONE LEFT.** Its 120,000-character
# limit is four times the summary's, so it bites on fewer changes and never on a small one — which
# is exactly why nothing noticed. The fix could not go in the file: it sat at the 200-line cap, and
# `AGENTS.md` rule 4 says split by concern rather than raise it. `infer/vertex.py` now holds the
# transport that `prompt_once.py` was already reaching into `gemini` for, which freed the room.

REVIEW_CAP = 120_000


def test_the_review_cap_is_four_times_the_summary_cap() -> None:
    """Both are pinned, and the relationship between them is the reason they differ."""
    assert gemini.MAX_DIFF_CHARS == REVIEW_CAP
    assert REVIEW_CAP == CAP * 4


def test_an_oversized_review_diff_reaches_the_model_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The prompt actually sent carries the marker. Asserted on the request, not on `capped`."""
    sent: dict[str, str] = {}

    def fake_post(url: str, bearer: str, body: dict[str, object]) -> dict[str, object]:
        contents = body["contents"]
        assert isinstance(contents, list)
        sent["prompt"] = contents[0]["parts"][0]["text"]
        return {
            "candidates": [{"content": {"parts": [{"text": "[]"}]}, "finishReason": "STOP"}],
            "_ms": 1,
        }

    monkeypatch.setattr(vertex, "token", lambda gcloud: "t")
    monkeypatch.setattr(gemini, "post", fake_post)

    gemini.read("x" * (REVIEW_CAP + 1_000), ["src/a.py"], project="p")

    assert TRUNCATED in sent["prompt"], "the model was sent a cut diff with no sign it was cut"


def test_a_review_diff_that_fits_is_sent_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    """The false-positive direction: an ordinary diff must not claim anything was hidden."""
    sent: dict[str, str] = {}

    def fake_post(url: str, bearer: str, body: dict[str, object]) -> dict[str, object]:
        contents = body["contents"]
        assert isinstance(contents, list)
        sent["prompt"] = contents[0]["parts"][0]["text"]
        return {
            "candidates": [{"content": {"parts": [{"text": "[]"}]}, "finishReason": "STOP"}],
            "_ms": 1,
        }

    monkeypatch.setattr(vertex, "token", lambda gcloud: "t")
    monkeypatch.setattr(gemini, "post", fake_post)

    gemini.read("+ one small change\n", ["src/a.py"], project="p")

    assert TRUNCATED not in sent["prompt"]
