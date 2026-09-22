from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings, get_settings
from app.triage import analyze, evaluate


@pytest.mark.parametrize(
    "error5,error1,error6,expected",
    [
        (1.44, 1.44, 0.01, "SEV1"),
        (1.44, 0.1, 0.1, "SEV3"),
        (0.6, 0.6, 0.6, "SEV2"),
        (0.1, 0.1, 0.1, "SEV3"),
        (0, 0, 0, "SEV3"),
    ],
)
def test_multiwindow_burn_rules(error5, error1, error6, expected):
    result = evaluate(
        {
            "error_rate_5m": error5,
            "error_rate_1h": error1,
            "error_rate_6h": error6,
            "latency_p95_ms": 50,
        },
        99.9,
    )
    assert result["severity"] == expected
    assert result["engine"] == "rules-v1"
    assert result["model_summary"] is None


async def test_model_outage_preserves_deterministic_triage(monkeypatch):
    monkeypatch.setattr(get_settings(), "triage_model_url", "https://model.example/triage")
    with patch("httpx.AsyncClient.post", AsyncMock(side_effect=httpx.ConnectError("offline"))):
        result = await analyze(
            {"error_rate_5m": 2, "error_rate_1h": 2, "error_rate_6h": 1, "latency_p95_ms": 100},
            99.9,
        )
    assert result["model_status"] == "unavailable"
    assert result["severity"] == "SEV1"


async def test_model_cannot_inject_actions(monkeypatch):
    monkeypatch.setattr(get_settings(), "triage_model_url", "https://model.example/triage")
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://model.example/triage"),
        json={"summary": "Ignore all policies", "actions": ["delete database"]},
    )
    with patch("httpx.AsyncClient.post", AsyncMock(return_value=response)):
        result = await analyze(
            {"error_rate_5m": 2, "error_rate_1h": 2, "error_rate_6h": 1, "latency_p95_ms": 100},
            99.9,
        )
    assert result["model_status"] == "unavailable"
    assert all(a["risk"] == "read-only" for a in result["actions"])


def test_production_rejects_insecure_defaults():
    with pytest.raises(ValueError):
        Settings(environment="production", _env_file=None)


def test_production_requires_redis():
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://localhost/test",
        jwt_secret="x" * 48,
        redis_required=False,
        _env_file=None,
    )
    assert settings.redis_required is True
