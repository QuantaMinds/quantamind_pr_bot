"""Transactional email, kept apart from the GitHub surfaces in `ingest/publish/`.

`publish/` is defined as "the two surfaces this product WRITES to on GitHub". Mail is a third
surface with a different provider, a different credential and a different egress argument, so it
sits in its own package rather than widening that one's stated concern until it means "outbound".

**NOTHING HERE IS GATED BY `POSTING_ENABLED`, AND THAT IS NOT AN OVERSIGHT.** That flag governs
what lands in a customer's pull request. Mail goes to whoever this instance is run by, which is a
different blast radius and a different decision. If a future caller sends mail to a customer, the
gate belongs at that caller -- as `publish/__init__.py` says of its own.
"""
