"""Which endpoint a model call goes to, and where the customer's key travels.

WHAT: `infer/vertex.endpoint` for our project and for a customer's Gemini key, and `post` failing on
      a refused key without the key reaching the error.
WHY:  **A BYOK CUSTOMER PAYS LESS BECAUSE THEY BRING THE MODEL.** A key ignored here runs their
      reviews on our GCP project at our cost; a key placed in the URL reaches access logs and
      exception text. Both are silent — the review still happens — so both are asserted.
IMPORTS: pytest, quantamind.infer.vertex, quantamind.types.admission.model_route.
CONSUMED BY: `just check`.
"""

from __future__ import annotations

import io
import urllib.error
from typing import Any

import pytest

from quantamind.infer import vertex
from quantamind.types.admission.model_route import GeminiKey, OurVertex

KEY = "AIza-customer-secret-9876"


def _where(route: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[str, dict[str, str]]:
    monkeypatch.setattr(vertex, "token", lambda gcloud: "our-bearer")
    return vertex.endpoint(
        route, project="our-project", location="us-central1", model="gemini-2.5-pro", gcloud="g"
    )


def test_a_customer_key_goes_to_the_gemini_api_in_a_header_never_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, auth = _where(GeminiKey(KEY), monkeypatch)

    assert url == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent"
    )
    assert auth == {"x-goog-api-key": KEY}
    assert KEY not in url


def test_our_route_and_no_route_both_bill_our_project(monkeypatch: pytest.MonkeyPatch) -> None:
    ours = _where(OurVertex("our-project"), monkeypatch)
    default = _where(None, monkeypatch)

    assert ours == default
    assert ours[0].startswith(
        "https://us-central1-aiplatform.googleapis.com/v1/projects/our-project/"
    )
    assert ours[1] == {"Authorization": "Bearer our-bearer"}


def test_a_refused_key_fails_by_name_without_the_key_in_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(request: Any, timeout: int) -> Any:
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"error":"API key not valid"}')
        )

    monkeypatch.setattr(vertex.urllib.request, "urlopen", refuse)
    url, auth = _where(GeminiKey(KEY), monkeypatch)

    with pytest.raises(vertex.InferenceFailed) as failed:
        vertex.post(url, auth, {"contents": []})

    assert "HTTP 400" in str(failed.value)
    assert KEY not in str(failed.value)
