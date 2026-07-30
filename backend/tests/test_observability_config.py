from unittest.mock import patch

from pydantic import SecretStr

from app.core.config import Settings
from app.observability.sentry import configure_sentry
from app.observability.telemetry import telemetry_configuration


def test_opentelemetry_is_disabled_without_an_external_collector(
    test_settings: Settings,
) -> None:
    config = telemetry_configuration(test_settings)

    assert config.enabled is False
    assert config.endpoint is None
    assert config.service_name == "fashion-network-api"


def test_opentelemetry_configuration_accepts_optional_otlp_exporter(
    test_settings: Settings,
) -> None:
    settings = test_settings.model_copy(
        update={
            "opentelemetry_enabled": True,
            "opentelemetry_exporter_otlp_endpoint": "http://collector:4318",
            "opentelemetry_trace_sample_ratio": 0.25,
        }
    )

    config = telemetry_configuration(settings)

    assert config.enabled is True
    assert config.endpoint == "http://collector:4318"
    assert config.sample_ratio == 0.25


def test_sentry_is_disabled_by_default(test_settings: Settings) -> None:
    with patch("app.observability.sentry.sentry_sdk.init") as initialize:
        assert configure_sentry(test_settings) is False

    initialize.assert_not_called()


def test_sentry_enables_privacy_safe_defaults(test_settings: Settings) -> None:
    settings = test_settings.model_copy(
        update={
            "sentry_enabled": True,
            "sentry_dsn": SecretStr("https://public@example.invalid/1"),
        }
    )

    with patch("app.observability.sentry.sentry_sdk.init") as initialize:
        assert configure_sentry(settings) is True

    kwargs = initialize.call_args.kwargs
    assert kwargs["send_default_pii"] is False
    assert kwargs["max_request_body_size"] == "never"
    assert kwargs["traces_sample_rate"] == 0.0
