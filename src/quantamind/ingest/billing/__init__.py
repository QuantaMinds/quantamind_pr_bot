"""The two calls this service makes to our own billing service, per pull request.

WHAT: `review_gate.authorize` before a review and `review_gate.settle` after it.
WHY:  **A PACKAGE, NOT A FILE IN `ingest/`**, so a second billing call does not have to argue for a
      slot in a directory near its cap. Nothing in here speaks to a payment processor.
IMPORTS: stdlib, types.deployment.
CONSUMED BY: `serve/review/admission.py`, `serve/review/review_delivery.py`.
"""
