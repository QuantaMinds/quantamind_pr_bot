"""Run the webhook endpoint until it is interrupted, and say plainly what it will post.

WHAT: `run(port)` reads the secret from the environment, binds the listener, prints the startup
      banner and serves until Ctrl-C. Returns the process exit code.
WHY:  **Split out of `cli.py` at the 200-line cap, and it is the right seam.** `cli.py` parses
      arguments and dispatches; this owns one command, including the one decision in it that is not
      mechanical -- what the banner is allowed to claim.

      **THE WORK CALLBACK CALLS `review_pull_request()`, AND THIS PARAGRAPH SAID OTHERWISE FOR
      MONTHS.** It clones on receipt, ranks, renders and posts. The banner was corrected when the
      drift was found by reading a running container's log -- see the comment above it -- but these
      two docstrings were not, so the file went on describing an inert endpoint while shipping a
      live one. A docstring is the first thing a reader trusts and the last thing a test reads.

      **The secret is read here, from the environment, and is deliberately absent from `Settings`**
      -- so it cannot reach `quantamind config` and be printed into a terminal scrollback or a CI
      log. There is no default: `build()` refuses to bind without one.
IMPORTS: types.settings, and serve.{listener,webhook_github} inside the function so `--version` and
      `config` do not pay for the socket layer.
CONSUMED BY: `serve/cli.py`.
"""

from __future__ import annotations

from quantamind.types.dotenv import credential
from quantamind.types.settings import load

# The webhook secret is read at serve time and never from `Settings`, so it cannot reach
# `quantamind config` and be printed into a terminal scrollback or a CI log.
#
# **IT IS READ THROUGH `credential()` AND NOT THE PROCESS ENVIRONMENT DIRECTLY, BECAUSE THIS FILE
# HELD THAT BUG.** `types/dotenv.from_file` deliberately never writes to the process environment,
# so a `.env` carrying QUANTAMIND_WEBHOOK_SECRET produced "refusing to bind" while looking
# perfectly configured. Every other setting in this product has read that file since the day it
# existed; these four did not. An exported value still wins, so no deployment changes meaning.
SECRET_VARIABLE = "QUANTAMIND_WEBHOOK_SECRET"


def run(port: int, host: str = "127.0.0.1") -> int:
    """Bind, and say plainly what this endpoint does and does not do.

    The work callback clones on receipt, ranks, renders and hands the result to `deliver()`. The
    banner states what posting will actually do, read from the setting rather than asserted here:
    under `QUANTAMIND_POSTING_ENABLED=0` it rehearses and prints what it would have posted. An
    endpoint that quietly accepted and dropped the work would be indistinguishable from one doing
    its job, which is why the banner is computed from behaviour and never written as a claim.
    """
    from quantamind.ingest.diff import DiffReadFailed
    from quantamind.ingest.publish.github_comments import CommentFailed
    from quantamind.serve.http.bind import build
    from quantamind.serve.review.gate import review_pull_request
    from quantamind.serve.webhook_github import MisconfiguredSecret
    from quantamind.serve.working_clone import CloneFailed
    from quantamind.types.forge.delivery import Review

    secret = credential(SECRET_VARIABLE)
    # **READ HERE, NOT FROM `Settings`, FOR THE REASON THE WEBHOOK SECRET IS.** A credential in a
    # settings object reaches a log the first time anybody prints one. Empty is a REFUSAL at the
    # provisioning routes rather than an open door -- see `serve/web/provision_route.py`.
    provision_secret = credential("QUANTAMIND_PROVISION_SECRET")
    accepted: list[Review] = []

    settings = load()

    def work(review: Review) -> None:
        accepted.append(review)
        print(
            f"[serve] accepted {review.repo}#{review.number} at {review.head_sha[:12]}", flush=True
        )
        # **A FAILURE HERE MUST NOT BE SWALLOWED AND MUST NOT KILL THE THREAD SILENTLY.** The
        # listener leaves the delivery without a `completed_at` when this raises, which makes
        # GitHub's redelivery a legitimate retry -- so the exception is allowed to propagate after
        # it has been named. What is NOT allowed is a bare except that turns a broken pipeline into
        # a quiet 202, which is indistinguishable from a working one.
        try:
            done = review_pull_request(review, settings)
        except (CloneFailed, CommentFailed, DiffReadFailed) as exc:
            print(f"[serve] {review.repo}#{review.number} FAILED: {exc}", flush=True)
            raise
        if done.body is not None and not settings.posting_enabled:
            print(f"[serve] --- comment it would have posted ---\n{done.body}", flush=True)
        print(f"[serve] {review.repo}#{review.number}: {done.sentence()}", flush=True)

    try:
        server = build(
            settings,
            secret,
            work,
            port=port,
            host=host,
            provision_secret=provision_secret,
        )
    except MisconfiguredSecret as exc:
        print(f"configuration error: {exc}\n\nSet {SECRET_VARIABLE} and try again.")
        return 1
    except OSError as exc:
        print(f"could not bind port {port}: {exc}")
        return 1

    # **`flush=True`, AND IT IS NOT DECORATION.** Python block-buffers stdout when it is a pipe
    # rather than a terminal, which is every real deployment -- systemd, Docker, CI, a log file.
    # `serve_forever()` then never returns, the 4 KB buffer never fills, and SIGTERM kills the
    # process without flushing: the banner is not merely late, it is LOST. Found by running the
    # command under a pipe, having passed every test that captured it in-process. The line this
    # cost is the one that matters most, invisible to exactly the operator who needed it.
    # `tests/unit/layers/serve/test_serve_banner.py` reads it through a real pipe.
    #
    # **THAT LINE SAID "IT DOES NOT REVIEW" LONG AFTER IT DID.** `deliver()` is wired below and has
    # been since the delivery path was joined, but the banner kept announcing the old behaviour --
    # so the one message an operator reads at startup told them the endpoint was inert while it
    # cloned, ranked and rendered. It was caught by running the container and reading its log, not
    # by any test: every test asserted the line was PRESENT, which it was, and none asked whether
    # it was true. It now states what posting will actually do, from the setting itself.
    #
    # `server_address[0]` is bytes on some address families; `build()` binds loopback, so the
    # host is stated rather than formatted out of the tuple.
    # **THE BANNER NAMES THE ADDRESS ACTUALLY BOUND.** It hardcoded 127.0.0.1, which was true
    # until the container asked for 0.0.0.0 -- at which point the log would have said loopback
    # while the socket listened everywhere, and the one place an operator checks would have been
    # the one place that lied.
    print(f"[serve] listening on {host}:{server.server_address[1]}", flush=True)
    print(
        "[serve] POST /webhook  — verifies the signature, refuses a replay, answers 202", flush=True
    )
    print(
        "[serve] GET  /health   — opens the store and reports what is wrong, never raises",
        flush=True,
    )
    print(
        "[serve] GET  /         — the dashboard: sign in, then a repository's reports",
        flush=True,
    )
    print(
        "[serve] GET  /r/<owner>/<name> — compliance, outcomes and cost for one repository",
        flush=True,
    )
    print(
        "[serve] GET  /scan?repo=owner/name — what the first history walk found, as JSON",
        flush=True,
    )
    print(
        "[serve] It REVIEWS: clone, rank, render. Posting is "
        + (
            "ON — comments are written to real pull requests."
            if settings.posting_enabled
            else "OFF — it prints the comment it would have posted and writes nothing."
        ),
        flush=True,
    )
    # **THE BANNER STATES WHAT THE ROUTE WILL ACTUALLY DO, COMPUTED FROM THE VALUE.** The line
    # above it about posting was wrong for months because it was written as a claim rather than
    # read from a setting, and an operator checking one line at startup read the one that lied.
    print(
        "[serve] POST /entitlement — "
        + (
            "records what the billing service says an account holds, and reads it back"
            if provision_secret
            else "503: no QUANTAMIND_PROVISION_SECRET, so no push can be authenticated"
        ),
        flush=True,
    )
    print(
        "[serve] http.server is not a hardened edge — run it behind a TLS-terminating proxy.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] stopping", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0
