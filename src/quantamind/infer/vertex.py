"""One authenticated call to Vertex, and the two failures it can end in.

WHAT: `endpoint(route, ...)` gives the URL and auth header for one call — our Vertex project, or
      the customer's own Gemini API key (BYOK). `post(url, headers, body)` makes the call and
      returns the parsed reply with its elapsed milliseconds attached. `Unavailable` and
      `InferenceFailed` are the two ways a model read ends badly.
WHY:  **`prompt_once.py` WAS IMPORTING `_post` AND `_token` OUT OF `gemini`.** A second module
      reaching into another's privates is the signal that those functions were never gemini's
      internals: they are the transport every model call shares, and gemini is one caller of it.

      **AND `gemini.py` DESCRIBED ITSELF WITH AN "AND".** It called Vertex AND built and parsed
      the review prompt, which is what `AGENTS.md` rule 6 names as the split condition. It sat at
      the 200-line cap, so the honest fix for the next change was to split by concern rather than
      raise the cap.

      **THE ERRORS LIVE HERE BECAUSE BOTH HALVES RAISE THEM.** `post` raises `InferenceFailed`
      on a bad HTTP reply and the parser raises it on a bad body; putting it with the transport
      keeps the import pointing left and out of a cycle, since `change_summary` already imports
      `gemini`.

      **THE ELAPSED TIME IS ATTACHED TO THE REPLY**, not measured by the caller: a caller timing
      it separately would be timing its own parsing too, and a cost that drifts from the bill is
      worse than no cost at all.

      **A CUSTOMER'S KEY GOES IN A HEADER, NEVER THE URL.** A URL is what reaches an access log or
      an exception message; `x-goog-api-key` does not. The Gemini API takes the same
      `generateContent` body and returns the same shape, so only the endpoint and the auth change.
IMPORTS: stdlib, `ingest.google_auth` for our credential, `types.admission.model_route`.
CONSUMED BY: `infer/gemini.py`, `infer/prompt_once.py`, `infer/change_review.py`,
      `serve/commands/run_commit.py`, `serve/deep_review.py`.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from quantamind.ingest import google_auth
from quantamind.types.admission.model_route import GeminiKey, ModelRoute
from quantamind.types.deployment import Destination, permit

MODEL = "gemini-2.5-pro"
TIMEOUT_S = 300
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"


class Unavailable(RuntimeError):
    """No credentials. Distinct from a model that ran and found nothing."""


class InferenceFailed(RuntimeError):
    """The model did not return usable findings. Never silently an empty review."""


def token(gcloud: str) -> str:
    """A bearer token from wherever we are running.

    **THIS SHELLED OUT TO `gcloud` AND NOTHING ELSE**, which meant the model half could only work
    on a machine with the SDK installed and a human logged in — never in the container, which is
    where the product actually runs. `ingest/google_auth` tries the GCP metadata server first, so
    a deployed container needs no credential on disk at all, and falls back to `gcloud` for
    laptop development.
    """
    try:
        got = google_auth.token(gcloud)
    except google_auth.Unavailable as exc:
        raise Unavailable(str(exc)) from None
    # **THE SOURCE IS LOGGED AND THE TOKEN IS NOT.** `Token` was built carrying its source "so it
    # can be logged" and then nothing logged it, which left no way to tell a container using the
    # metadata server from one that had somehow found a `gcloud` — the exact difference a
    # deployment is trying to prove. The value never appears; only which identity answered.
    print(f"[infer] access token from {got.source}", flush=True)
    return got.value


def endpoint(
    route: ModelRoute | None, *, project: str, location: str, model: str, gcloud: str
) -> tuple[str, dict[str, str]]:
    """Where one call goes, and how it authenticates. None or `OurVertex` is our project."""
    if isinstance(route, GeminiKey):
        return f"{GEMINI_API}/models/{model}:generateContent", {"x-goog-api-key": route.api_key}
    ours = route.project if route is not None else project
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1/projects/{ours}"
        f"/locations/{location}/publishers/google/models/{model}:generateContent"
    )
    return url, {"Authorization": f"Bearer {token(gcloud)}"}


def post(url: str, auth: dict[str, str], body: dict[str, object]) -> dict[str, object]:
    """One call. **The elapsed time is attached to the reply**: a caller timing it separately would
    be timing its own parsing too, and a cost that drifts from the bill is worse than none."""
    started = time.monotonic()
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={**auth, "Content-Type": "application/json"},
    )
    try:
        # **ASK BEFORE THE SOCKET OPENS.** D7f: an air-gapped deployment REFUSES
        # this, rather than attempting it and failing somewhere the customer sees
        # in their egress log and we do not.
        permit(Destination.INFERENCE)
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            parsed = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise InferenceFailed(f"HTTP {exc.code}: {exc.read()[:200]!r}") from None
    if not isinstance(parsed, dict):
        raise InferenceFailed(f"expected an object, got {type(parsed).__name__}")
    parsed["_ms"] = int((time.monotonic() - started) * 1000)
    return parsed
