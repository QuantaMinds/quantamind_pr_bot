"""Every table this build creates, as the DDL text a fresh store is made from.

WHAT: `TABLES`, one `CREATE TABLE` statement per table, applied by `store/schema.create()` and
      re-used verbatim by each migration step so a migrated store is byte-identical to a fresh one.
WHY:  **IT LEFT `schema.py` WHEN THAT FILE HIT THE 200-LINE CAP AND THE NEXT TABLE HAD NOWHERE TO
      GO.** The alternative was trimming the comments that explain why each table has the shape it
      does, and those are the reason the file is worth reading. `AGENTS.md` rule 4: split by
      concern, do not raise the cap. The concerns are the DDL and the versioning that applies it.

      **`scripts/guard/records/check_schema_shape.py` FOLLOWS THE DDL, NOT THE FILENAME.** Its
      digest is computed over the extracted `CREATE` statements, so this move did not change it —
      and it refuses outright if it finds no `CREATE` statement, which is what stops it quietly
      watching the wrong file after a move like this one.
IMPORTS: nothing. Text only — this file names no connection and executes nothing, so it
      still needs no database handle and stays testable without one.
CONSUMED BY: `store/schema.py`, `store/migrations/steps.py`, `store/drift.py`, and the golden.
"""

from __future__ import annotations

TABLES: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS repo (
        id INTEGER PRIMARY KEY, host TEXT NOT NULL, name TEXT NOT NULL,
        clone_filter TEXT NOT NULL DEFAULT '', first_seen INTEGER NOT NULL,
        languages_parsed TEXT NOT NULL DEFAULT '', UNIQUE (host, name))""",
    """CREATE TABLE IF NOT EXISTS review (
        id INTEGER PRIMARY KEY, repo_id INTEGER NOT NULL REFERENCES repo(id),
        pr_number INTEGER NOT NULL, head_sha TEXT NOT NULL, created_at INTEGER NOT NULL,
        fire_decision INTEGER NOT NULL, coverage_pct REAL, request_count INTEGER NOT NULL
        DEFAULT 0, tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER, tier TEXT NOT NULL DEFAULT 'free',
        UNIQUE (repo_id, pr_number, head_sha))""",
    # Every changed unit, funded or not. `allocation` is deep | shallow | cold.
    """CREATE TABLE IF NOT EXISTS ranked_unit (
        review_id INTEGER NOT NULL REFERENCES review(id), unit_path TEXT NOT NULL,
        unit_name TEXT, rank INTEGER NOT NULL, score REAL NOT NULL, percentile REAL,
        allocation TEXT NOT NULL, PRIMARY KEY (review_id, unit_path, rank))""",
    # Every declared rule against every changed file, including the ones we could not decide.
    # **ALL FOUR OUTCOMES ARE STORED, OR THE DENOMINATOR IS A GUESS.** A trail holding only
    # violations cannot answer "was this rule enforced", only "did it fire", and a compliance rate
    # computed from it would be over whatever population the reader assumed.
    # `provenance` is what makes the trail worth reading: a parser's verdict can be re-run on the
    # same commit and shown to agree, and a model's cannot.
    """CREATE TABLE IF NOT EXISTS rule_check (
        review_id INTEGER NOT NULL REFERENCES review(id), rule_id TEXT NOT NULL,
        path TEXT NOT NULL, line INTEGER NOT NULL DEFAULT 0, outcome TEXT NOT NULL,
        evidence TEXT NOT NULL DEFAULT '', reason TEXT, provenance TEXT NOT NULL,
        PRIMARY KEY (review_id, rule_id, path))""",
    # What happened to the change AFTER we spoke. Separate from `review` because `review` records
    # a decision we made at one instant and this records facts that arrive later and change --
    # and because adding columns to an existing table by ALTER produces DDL text that differs from
    # a freshly created one in ways `drift` reports and nobody would predict.
    """CREATE TABLE IF NOT EXISTS lifecycle (
        review_id INTEGER PRIMARY KEY REFERENCES review(id), posted_at INTEGER,
        merge_state TEXT NOT NULL DEFAULT 'unknown', merged_at INTEGER,
        observed_at INTEGER NOT NULL)""",
    # One row per observation, never one row per review: "still running" is a statement about an
    # instant, and overwriting it would destroy the only evidence of what it said before it broke.
    """CREATE TABLE IF NOT EXISTS prod_signal (
        id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES review(id),
        observed_at INTEGER NOT NULL, state TEXT NOT NULL, source TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS finding (
        id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES review(id),
        unit_path TEXT NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL,
        published INTEGER NOT NULL DEFAULT 0, confidence TEXT NOT NULL,
        provenance TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS claim (
        id INTEGER PRIMARY KEY, finding_id INTEGER NOT NULL REFERENCES finding(id),
        claim_kind TEXT NOT NULL, verdict TEXT NOT NULL, reason TEXT NOT NULL)""",
    # Typed silence. "No edge here" and "we failed here" are different rows, never the same absence.
    """CREATE TABLE IF NOT EXISTS unresolved (
        review_id INTEGER NOT NULL REFERENCES review(id), site TEXT NOT NULL,
        reason TEXT NOT NULL, construct TEXT NOT NULL)""",
    # The table the product exists to fill. `source` is git | datadog | manual.
    """CREATE TABLE IF NOT EXISTS outcome (
        review_id INTEGER NOT NULL REFERENCES review(id), unit_path TEXT NOT NULL,
        fix_sha TEXT NOT NULL, fix_at INTEGER NOT NULL, fix_subject TEXT NOT NULL,
        source TEXT NOT NULL, matched_rank INTEGER, rule_version INTEGER NOT NULL,
        PRIMARY KEY (review_id, unit_path, fix_sha))""",
    """CREATE TABLE IF NOT EXISTS reaction (
        review_id INTEGER NOT NULL REFERENCES review(id), finding_id INTEGER REFERENCES finding(id),
        kind TEXT NOT NULL, actor_hash TEXT NOT NULL, at INTEGER NOT NULL)""",
    # Ranks 1..k for k >= 3, with score and percentile. A top-1 row halves shadow evaluation.
    """CREATE TABLE IF NOT EXISTS shadow_pick (
        review_id INTEGER NOT NULL REFERENCES review(id), ranker_name TEXT NOT NULL,
        unit_path TEXT NOT NULL, rank INTEGER NOT NULL, score REAL NOT NULL, percentile REAL,
        PRIMARY KEY (review_id, ranker_name, rank))""",
    # Token counts, never cents. Cost is derived at read time from these.
    """CREATE TABLE IF NOT EXISTS request (
        id INTEGER PRIMARY KEY, review_id INTEGER NOT NULL REFERENCES review(id),
        ordinal INTEGER NOT NULL, model TEXT NOT NULL, model_version TEXT NOT NULL,
        effort TEXT, tokens_in INTEGER NOT NULL, tokens_out INTEGER NOT NULL,
        cache_read_tokens INTEGER NOT NULL DEFAULT 0,
        cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER, stop_reason TEXT, UNIQUE (review_id, ordinal))""",
    # Webhook deliveries we have seen, keyed by GitHub's X-GitHub-Delivery GUID.
    # `completed_at` NULL means we started and did not finish: GitHub redelivers on failure and
    # REUSES the same GUID, so an unfinished attempt must be retryable while a finished one must
    # not be replayable.
    # B2. **THE SESSION TOKEN IS NEVER STORED, ONLY ITS HASH.** A stolen database must not hand
    # anyone a live session, which is the same reason `app_key_path` holds a path and not a key.
    # `expires_at` is written at issue: a session with no end is a credential with no end.
    """CREATE TABLE IF NOT EXISTS account (
        login TEXT PRIMARY KEY, github_id INTEGER NOT NULL,
        first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS session (
        token_hash TEXT PRIMARY KEY, login TEXT NOT NULL REFERENCES account(login),
        created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL)""",
    # `eligible` NULL is "never assessed", 0 is "refused". → `store/installations.py`.
    """CREATE TABLE IF NOT EXISTS installation (
        account TEXT NOT NULL, repo TEXT NOT NULL, tier TEXT NOT NULL DEFAULT 'free',
        eligible INTEGER, reasons TEXT NOT NULL DEFAULT '', first_seen INTEGER NOT NULL,
        removed_at INTEGER, PRIMARY KEY (account, repo))""",
    """CREATE TABLE IF NOT EXISTS delivery (
        delivery_id TEXT PRIMARY KEY, event TEXT NOT NULL, started_at INTEGER NOT NULL,
        completed_at INTEGER)""",
    # B3. One row per subscription, written ONLY from an authenticated Stripe delivery.
    # **`standing` IS A NAME AND NOT A BOOLEAN**: "they cancelled" and "their card failed on
    # Tuesday" need different answers from us, and a column that cannot tell them apart forces a
    # guess at exactly the moment a customer is deciding whether to stay. **NOTHING WRITES IT NOW**
    # -> "The schema, and one table nothing writes" in `docs/engineering/CODEBASE.md`.
    # **`event_at` IS STRIPE'S TIMESTAMP AND IT IS LOAD-BEARING.** Stripe does not guarantee
    # delivery order, so `store/subscriptions.record` refuses to let an older event overwrite a
    # newer one. Without this column that comparison cannot be made and a redelivered `canceled`
    # switches off a live customer.
    # **`amount_cents` IS RECORDED, NOT DERIVED FROM THE PRICE ID.** A price id pointing at the
    # wrong product is configuration this product cannot detect; storing what Stripe actually
    # charged makes it visible in the row rather than only on somebody's invoice.
    """CREATE TABLE IF NOT EXISTS subscription (
        account TEXT NOT NULL, subscription_id TEXT NOT NULL, customer_id TEXT NOT NULL,
        price_id TEXT NOT NULL, standing TEXT NOT NULL, seats INTEGER NOT NULL DEFAULT 1,
        amount_cents INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT 'usd',
        current_period_end INTEGER NOT NULL DEFAULT 0, event_at INTEGER NOT NULL,
        PRIMARY KEY (account, subscription_id))""",
    # **THE NEXT THREE ARE KEYED `(forge, account)`, AND THAT IS NOT PREMATURE.** A Bitbucket
    # workspace `acme` and a GitHub organisation `acme` are different customers who may both
    # install us. Adding the column later means a second migration plus a window in which every
    # row is ambiguous about whose it is, so it is here from the first row written.
    #
    # What the billing service last told us about an account. `as_of` is when it last spoke and
    # `grace_until` is how long a paid account keeps its tier when it has not spoken since --
    # a push that never arrived is our failure, and charging the customer for it by withdrawing
    # their reviews is the wrong way round. Never deleted: a lapsed account keeps its row.
    """CREATE TABLE IF NOT EXISTS entitlement (
        forge TEXT NOT NULL, account TEXT NOT NULL, tier TEXT NOT NULL, state TEXT NOT NULL,
        seats_included INTEGER, payment_ref TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '', as_of INTEGER NOT NULL, valid_through INTEGER,
        grace_until INTEGER, PRIMARY KEY (forge, account))""",
    # One row per developer per billing period. **`actor_hash` IS A SALTED HASH AND NEVER A
    # LOGIN.** `docs/plans/design/commercial-surface.md`: "a tool that measures where code needs
    # rework must never become a tool that measures which developer causes it". A seat count does
    # not need an identity, and holding one would make this table answer a question nobody asked.
    """CREATE TABLE IF NOT EXISTS seat_use (
        forge TEXT NOT NULL, account TEXT NOT NULL, period TEXT NOT NULL,
        actor_hash TEXT NOT NULL, repo TEXT NOT NULL, first_seen INTEGER NOT NULL,
        PRIMARY KEY (forge, account, period, actor_hash))""",
    # The installation itself, which `installation` (keyed account,repo) never held.
    # **`installation_ref` IS TEXT, NOT INTEGER**: GitHub's installation id is a number and a
    # Forge installation context is not, and a column that fits one forge is a column the second
    # forge has to work around. `seat_salt` is persisted rather than read from the environment --
    # a salt that rotates on deploy makes every developer look new and overbills the customer.
    """CREATE TABLE IF NOT EXISTS forge_installation (
        forge TEXT NOT NULL, account TEXT NOT NULL, installation_ref TEXT NOT NULL,
        account_id TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT '',
        seat_salt TEXT NOT NULL, first_seen INTEGER NOT NULL, removed_at INTEGER,
        PRIMARY KEY (forge, account))""",
    # The touch index the ranker counts over. Written by store.touches from ingest.history.
    """CREATE TABLE IF NOT EXISTS touch (
        repo_id INTEGER NOT NULL REFERENCES repo(id), path TEXT NOT NULL,
        committed_at INTEGER NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS touch_lookup ON touch (repo_id, path, committed_at)",
    # How far the touch index was built, so the next review can extend it instead of re-reading
    # 338,907 touches. **`head_sha` IS A COMMIT, NOT A TIMESTAMP**: git history is not
    # chronologically ordered, so a rebase or cherry-pick lands commits whose committer date is
    # OLDER than rows already indexed, and a time watermark would skip them and read low forever.
    # `languages` is here because a suffix added to the product leaves every existing index
    # incomplete for it, and an incremental read would never backfill it -- the one staleness with
    # no natural symptom.
    """CREATE TABLE IF NOT EXISTS touch_watermark (
        repo_id INTEGER PRIMARY KEY REFERENCES repo(id), head_sha TEXT NOT NULL,
        languages TEXT NOT NULL, indexed_at INTEGER NOT NULL)""",
)
