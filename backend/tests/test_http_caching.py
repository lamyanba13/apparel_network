from datetime import UTC, datetime

from fastapi import Response
from fastapi.testclient import TestClient

from app.common.api import DeprecationPolicy, apply_deprecation_headers
from app.common.caching import generate_etag, if_none_match_matches
from app.core.config import Settings
from app.main import create_application


def test_etag_helpers_generate_and_compare_opaque_values() -> None:
    etag = generate_etag("catalog-v1")

    assert etag.startswith('"')
    assert if_none_match_matches(etag, etag)
    assert if_none_match_matches(f"W/{etag}", etag)
    assert if_none_match_matches("*", etag)
    assert not if_none_match_matches('"different"', etag)


def test_etag_middleware_is_opt_in_and_returns_304(
    test_settings: Settings,
) -> None:
    enabled_settings = test_settings.model_copy(update={"etag_enabled": True})
    application = create_application(enabled_settings)
    etag = generate_etag("catalog-v1")

    @application.get("/_test/catalog", include_in_schema=False)
    async def catalog() -> Response:
        return Response(
            content="catalog-v1",
            media_type="text/plain",
            headers={"ETag": etag},
        )

    with TestClient(application) as client:
        initial = client.get("/_test/catalog")
        cached = client.get(
            "/_test/catalog",
            headers={"If-None-Match": etag},
        )

    assert initial.status_code == 200
    assert initial.headers["ETag"] == etag
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["ETag"] == etag


def test_deprecation_and_sunset_headers_are_explicit() -> None:
    response = Response()
    policy = DeprecationPolicy(
        deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
        sunset_at=datetime(2026, 6, 1, tzinfo=UTC),
        documentation_url="https://api.example.com/deprecations/v1",
    )

    apply_deprecation_headers(response, policy)

    assert response.headers["Deprecation"].startswith("@")
    assert response.headers["Sunset"] == "Mon, 01 Jun 2026 00:00:00 GMT"
    assert 'rel="deprecation"' in response.headers["Link"]
