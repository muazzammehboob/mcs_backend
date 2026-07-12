"""Tests for BYOK header validation.

Implements consolidated spec §5 (BYOK & Key Handling).
Acceptance criteria:
- Missing header returns 401
- Present header passes through to handler
- API key value never appears in log output
"""

import logging

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_missing_header_returns_401(client: AsyncClient) -> None:
    """Protected endpoint returns 401 when X-Gemini-Api-Key is absent."""
    response = await client.get("/protected-stub")
    assert response.status_code == 401
    data = response.json()
    assert "X-Gemini-Api-Key" in data["detail"]


@pytest.mark.asyncio
async def test_present_header_passes_through(client: AsyncClient) -> None:
    """Protected endpoint returns the key when header is present."""
    test_key = "test-api-key-12345"
    response = await client.get(
        "/protected-stub",
        headers={"X-Gemini-Api-Key": test_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["received_key"] == test_key


@pytest.mark.asyncio
async def test_api_key_not_in_logs(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The literal API key value never matches any emitted log line."""
    caplog.set_level(logging.DEBUG)
    distinctive_key = "ak-test-not-in-logs-9876543210"

    await client.get(
        "/protected-stub",
        headers={"X-Gemini-Api-Key": distinctive_key},
    )

    for record in caplog.records:
        assert distinctive_key not in record.message, (
            f"API key leaked into log: {record.message}"
        )
        if record.args:
            args_str = str(record.args)
            assert distinctive_key not in args_str, (
                f"API key leaked into log args: {args_str}"
            )
