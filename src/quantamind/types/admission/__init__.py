"""What billing decided about one pull request, and which model that review may use.

WHAT: `decision.Admission` — full, free or refused, with the reason and the credit reservation —
      and `model_route.ModelRoute`, ours or the customer's own key.
WHY:  **`types/` IS AT ITS FIFTEEN-FILE CAP, SO THIS IS A PACKAGE.** The two belong together anyway:
      the model a review may call is part of what it was admitted to.
IMPORTS: stdlib only.
CONSUMED BY: `serve/review/admission.py`, `serve/review/review_delivery.py`, `infer/`.
"""
