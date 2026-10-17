"""API compatibility and user-visible error classification without live requests."""
from types import SimpleNamespace
from unittest.mock import Mock
import traceback

import httpx
import pytest
from openai import (APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError,
                    InternalServerError, NotFoundError, PermissionDeniedError, RateLimitError)

from app.errors import LLMUnavailableError
from app.services import llm_service


def api_error(error_type, status, code=None, parameter=None):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return error_type("SECRET provider message", response=httpx.Response(status, request=request),
                      body={"message": "SECRET", "code": code, "param": parameter})


def install_client(monkeypatch, create):
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_service, "client", client)


def test_gpt6_call_uses_supported_defaults_and_retains_requested_model(monkeypatch):
    def provider(**kwargs):
        if "temperature" in kwargs:
            raise api_error(BadRequestError, 400, "unsupported_value", "temperature")
        assert kwargs["model"] == "gpt-6-luna"
        assert kwargs["messages"] == [{"role": "user", "content": "Reply OK"}]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="OK"))])
    create = Mock(side_effect=provider)
    install_client(monkeypatch, create)
    assert llm_service.ask_llm("Reply OK") == "OK"
    assert create.call_count == 1


@pytest.mark.parametrize("error_type,status,code,param,expected", [
    (BadRequestError, 400, "unsupported_value", "temperature", "temperature"),
    (AuthenticationError, 401, "invalid_api_key", None, "hitelesítést"),
    (PermissionDeniedError, 403, None, None, "jogosultságait"),
    (NotFoundError, 404, "model_not_found", "model", "modell nevét"),
    (RateLimitError, 429, "insufficient_quota", None, "számlázási"),
    (RateLimitError, 429, "credit_balance_exhausted", None, "számlázási"),
    (RateLimitError, 429, "project_spend_limit_exceeded", None, "számlázási"),
    (RateLimitError, 429, "rate_limit_exceeded", None, "sebességkorlátot"),
    (InternalServerError, 503, "server_is_overloaded", None, "szerverhibát"),
    (BadRequestError, 400, "SECRET", "SECRET", "paramétert"),
])
def test_errors_are_specific_and_do_not_expose_provider_body(monkeypatch, error_type, status, code, param, expected):
    create = Mock(side_effect=api_error(error_type, status, code, param))
    install_client(monkeypatch, create)
    with pytest.raises(LLMUnavailableError) as captured:
        llm_service.ask_llm("PRIVATE DOCUMENT")
    assert expected in str(captured.value)
    assert f"http_status={status}" in captured.value.detail
    assert "SECRET" not in str(captured.value.to_dict())
    assert "SECRET" not in "".join(traceback.format_exception(captured.value))
    assert "PRIVATE DOCUMENT" not in captured.value.detail


@pytest.mark.parametrize("error_type,expected", [(APIConnectionError, "hálózatot"), (APITimeoutError, "időtúllépés")])
def test_connection_and_timeout_errors_are_distinct(monkeypatch, error_type, expected):
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    install_client(monkeypatch, Mock(side_effect=error_type(request=request)))
    with pytest.raises(LLMUnavailableError, match=expected):
        llm_service.ask_llm("test")


def test_missing_key_remains_configuration_error(monkeypatch):
    monkeypatch.setattr(llm_service, "client", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMUnavailableError, match="OPENAI_API_KEY"):
        llm_service.ask_llm("test")
