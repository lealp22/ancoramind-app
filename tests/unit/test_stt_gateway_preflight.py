"""Local smoke preflight never sends the configured alias to inference."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest

from scripts.stt_gateway_preflight import ALIAS, main


@pytest.mark.parametrize("denied_status", [403, 200])
def test_preflight_scope_cleanup_and_no_authorized_inference(denied_status):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/health/liveliness":
            return httpx.Response(200)
        if request.url.path == "/key/generate":
            return httpx.Response(200, json={"key": "sk-synthetic"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": ALIAS}]})
        assert request.url.path == "/v1/audio/transcriptions"
        assert b"not-authorized" in request.content
        assert ALIAS.encode() not in request.content
        return httpx.Response(denied_status)

    client = httpx.Client(base_url="http://127.0.0.1:4001", transport=httpx.MockTransport(handle))
    process = Mock(return_value=SimpleNamespace(returncode=0))
    with (
        patch(
            "scripts.stt_gateway_preflight.Settings",
            return_value=SimpleNamespace(openrouter_api_key="synthetic-upstream"),
        ),
        patch("scripts.stt_gateway_preflight.subprocess.run", process),
        patch("scripts.stt_gateway_preflight.httpx.Client", return_value=client),
    ):
        if denied_status == 403:
            main()
        else:
            with pytest.raises(RuntimeError, match="alias_denial_failed"):
                main()
    assert process.call_args_list[-1].args[0][-3:] == ["down", "--volumes", "--remove-orphans"]
    assert len(requests) == 4
