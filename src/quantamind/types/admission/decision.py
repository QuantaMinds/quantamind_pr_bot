"""Whether one pull request is reviewed, how fully, and what it costs.

WHAT: `Admission` and its `Mode`: FULL (a model review), FREE (deterministic only) or REFUSED
      (nothing reviewed; the comment says why).
WHY:  **THE REASON IS A CODE, NOT A SENTENCE.** `render/not_entitled.py` turns it into the comment,
      and the code is what a test asserts. A sentence built here would be tested as prose.

      **`unmetered` IS NAMED, BECAUSE IT IS THE ONE PATH THAT GIVES A REVIEW AWAY.** When billing
      cannot be reached, a paying account is reviewed anyway on our model and nothing is charged.
      That is deliberate — our outage is not their bill — and it must show up in a log as exactly
      that, never as an ordinary review.
IMPORTS: types.admission.model_route.
CONSUMED BY: `serve/review/admission.py`, `serve/review/review_delivery.py`,
      `render/not_entitled.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quantamind.types.admission.model_route import ModelRoute


class Mode(Enum):
    FULL = "full"
    FREE = "free"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class Admission:
    """What billing said about one pull request. Built only by `serve/review/admission.py`."""

    mode: Mode
    reason: str
    """Billing's reason code, e.g. `seat_full`, `no_credits`, `free_public`, `removed`."""

    author_login: str = ""
    seats_used: int = 0
    seats_included: int = 0
    resets_at: str = ""
    reservation_key: str = ""
    """Set when a credit was reserved. Handed back to billing when the outcome is known."""

    model_route: ModelRoute | None = None
    """Set for FULL. None means no model may be called."""

    unmetered: bool = False
    """Billing was unreachable and this paid account is being reviewed free of charge."""

    @property
    def calls_model(self) -> bool:
        return self.mode is Mode.FULL and self.model_route is not None
