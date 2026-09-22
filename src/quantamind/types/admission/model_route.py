"""Which model a review calls, and with whose credentials.

WHAT: `OurVertex(project)` — our Gemini on Vertex, billed to our GCP project — or
      `GeminiKey(api_key)` — the same model through the customer's own Gemini API key (BYOK).
WHY:  **THE CUSTOMER'S KEY IS A VALUE PASSED DOWN, NEVER A SETTING.** It arrives in the billing
      service's answer for one review and must not outlive it. `Settings` is printed by
      `quantamind config`; a key on it would reach a terminal the first time anyone ran it — the
      argument `ingest/app_auth.py` makes about the App's private key.

      **`repr` NEVER SHOWS THE KEY.** A dataclass prints every field by default, and a route logged
      while debugging would put the customer's key in our logs.
IMPORTS: stdlib only.
CONSUMED BY: `infer/vertex.py` and the review steps that call a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OurVertex:
    """Our model, on our GCP project."""

    project: str


@dataclass(frozen=True, slots=True)
class GeminiKey:
    """The customer's own Gemini API key. Never printed, never stored."""

    api_key: str = field(repr=False)

    def __repr__(self) -> str:
        return f"GeminiKey(…{self.api_key[-4:]})" if self.api_key else "GeminiKey(<empty>)"


ModelRoute = OurVertex | GeminiKey
