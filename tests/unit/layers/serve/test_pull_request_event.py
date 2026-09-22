"""A real `pull_request` delivery, read into a `Review` with its author.

WHAT: `serve/pull_request_event.reviewed` against a delivery captured from the App's own log
      (`tests/fixtures/github_pull_request_opened.json`, PR #111 on QuantaMinds/quantamind_pr_bot).
WHY:  **BILLING DECIDES ON THE AUTHOR, AND EVERY OTHER TEST BUILDS ITS OWN PAYLOAD.** A suite that
      only reads payloads it wrote tests itself. This one is GitHub's bytes, so a field that moved
      or was renamed fails here rather than as every developer silently reading as author "".

      **`private` MUST FAIL CLOSED.** A missing visibility is treated as private, so a gap in a
      payload can refuse a free review but can never give one away for private code.
IMPORTS: pytest, quantamind.serve.pull_request_event, quantamind.types.forge.delivery.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from quantamind.serve.pull_request_event import reviewed
from quantamind.types.forge.delivery import Ignore, Review

FIXTURE = Path(__file__).parents[3] / "fixtures" / "github_pull_request_opened.json"


def _payload() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(FIXTURE.read_text())
    return loaded


def test_a_real_delivery_names_its_author_by_id() -> None:
    got = reviewed(_payload())

    assert got == Review(
        repo="QuantaMinds/quantamind_pr_bot",
        number=111,
        head_sha=_payload()["pull_request"]["head"]["sha"],
        author_id="81304542",
        author_login="Dhanush295",
        author_is_bot=False,
        private=False,
        account="QuantaMinds",
        installation_id=157102851,
    )


def test_a_bot_is_recognised_by_what_github_says_not_by_its_name() -> None:
    bot = _payload()
    bot["pull_request"]["user"] = {"login": "dependabot[bot]", "id": 49699333, "type": "Bot"}
    human_with_bot_name = _payload()
    human_with_bot_name["pull_request"]["user"] = {"login": "build-bot", "id": 7, "type": "User"}

    outcomes = [reviewed(bot), reviewed(human_with_bot_name)]

    assert [o.author_is_bot for o in outcomes if isinstance(o, Review)] == [True, False]


def test_visibility_fails_closed_when_the_payload_does_not_say() -> None:
    silent = _payload()
    del silent["repository"]["private"]
    odd = _payload()
    odd["repository"]["private"] = "no"

    assert [getattr(reviewed(p), "private", None) for p in (silent, odd)] == [True, True]


def test_missing_author_and_installation_read_as_empty_rather_than_crashing() -> None:
    bare = _payload()
    bare["pull_request"]["user"] = None
    bare["installation"] = "not an object"

    got = reviewed(bare)

    assert isinstance(got, Review)
    assert (got.author_id, got.author_login, got.installation_id) == ("", "", 0)


def test_a_draft_and_an_irrelevant_action_are_ignored_with_a_reason() -> None:
    draft = copy.deepcopy(_payload())
    draft["pull_request"]["draft"] = True
    labelled = _payload()
    labelled["action"] = "labeled"

    reasons = [reviewed(draft), reviewed(labelled)]

    assert [r.reason for r in reasons if isinstance(r, Ignore)] == [
        "the pull request is a draft",
        "action 'labeled' does not change the code under review",
    ]


def test_the_owner_falls_back_to_the_repository_path() -> None:
    assert Review(repo="acme/widgets", number=1, head_sha="a").owner == "acme"
    assert Review(repo="acme/widgets", number=1, head_sha="a", account="Acme").owner == "Acme"
