"""Disposable Phoenix 15.1.0: auth, masked OTLP, alias cost and user deletion.

Explicit local-only experiment: python -m scripts.phoenix_spike.local_backend
Creates/removes only its own uniquely named container, loopback ports and SQLite
scratch data. No mounts, production credentials, LLM or app configuration.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import time
from uuid import uuid4

import httpx
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from scripts.phoenix_spike.exporter import SyntheticMaskedExporter, user_pseudonym

IMAGE = "arizephoenix/phoenix:version-15.1.0"


def docker(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )
    if result.returncode:
        raise RuntimeError("Local synthetic Docker operation failed")
    return result.stdout.strip()


def main() -> None:
    name = "ancoramind-phoenix-spike-" + uuid4().hex[:10]
    synthetic_env = {
        "PHOENIX_ENABLE_AUTH": "true",
        "PHOENIX_SECRET": secrets.token_hex(32),
        "PHOENIX_ADMIN_SECRET": secrets.token_hex(32),
        "PHOENIX_TELEMETRY_ENABLED": "false",
        "PHOENIX_ALLOW_EXTERNAL_RESOURCES": "false",
        "PHOENIX_DEFAULT_ADMIN_INITIAL_PASSWORD": secrets.token_urlsafe(24),
    }
    args = [
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "ancoramind.scope=synthetic-spike",
        "-p",
        "127.0.0.1::6006",
        "-p",
        "127.0.0.1::4317",
    ]
    for key in synthetic_env:
        args.extend(["-e", key])  # Values travel in child env, not CLI/output/files.
    provider = None
    try:
        docker(*args, IMAGE, env={**os.environ, **synthetic_env})
        ports = json.loads(docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", name))
        url = "http://127.0.0.1:" + ports["6006/tcp"][0]["HostPort"]
        grpc_endpoint = "http://127.0.0.1:" + ports["4317/tcp"][0]["HostPort"]
        with httpx.Client(base_url=url, trust_env=False, timeout=10) as client:
            deadline = time.monotonic() + 90
            while True:
                try:
                    ready = client.get("/openapi.json").status_code == 200
                except httpx.HTTPError:
                    ready = False
                if ready:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("Local Phoenix readiness timed out")
                time.sleep(1)
            unauthorized = client.get("/v1/projects").status_code
            assert unauthorized in {401, 403}
            client.headers["Authorization"] = "Bearer " + synthetic_env["PHOENIX_ADMIN_SECRET"]
            response = client.post(
                "/graphql",
                json={
                    "query": "mutation($input: CreateApiKeyInput!) { "
                    "createSystemApiKey(input: $input) { jwt } }",
                    "variables": {"input": {"name": "synthetic-spike"}},
                },
            )
            payload = response.json()
            assert not payload.get("errors"), "Local system-key creation failed"
            api_key = payload["data"]["createSystemApiKey"]["jwt"]
            wrapper = SyntheticMaskedExporter(
                OTLPSpanExporter(
                    endpoint=grpc_endpoint,
                    insecure=True,
                    timeout=2,
                    headers={"authorization": "Bearer " + api_key},
                )
            )
            provider = TracerProvider(resource=Resource({"service.name": "synthetic-spike"}))
            provider.add_span_processor(SimpleSpanProcessor(wrapper))
            tracer = provider.get_tracer("synthetic-spike")
            key = secrets.token_bytes(32)
            target = user_pseudonym("synthetic-target", key)
            other = user_pseudonym("synthetic-other", key)
            for user, cost in [(target, None), (target, 0.001), (other, None)]:
                attrs = {
                    "ancora.capture.source": "synthetic_text",
                    "openinference.span.kind": "LLM",
                    "user.id": user,
                    "llm.model_name": "ancoramind-default-r4",
                    "llm.token_count.prompt": 3,
                    "llm.token_count.completion": 2,
                    "llm.input_messages.0.message.content": "DNI sintético 12345678Z",
                }
                if cost is not None:
                    attrs["llm.cost.total"] = cost
                with tracer.start_as_current_span("synthetic", attributes=attrs):
                    pass
            assert wrapper.exported == 3 and wrapper.failures == 0
            # Ingestion is asynchronous; polling is read-only, never resends spans.
            for _ in range(30):
                result = client.get("/v1/projects/spike/spans")
                data = result.json().get("data", []) if result.status_code == 200 else []
                if len(data) == 3:
                    break
                time.sleep(0.2)
            assert len(data) == 3, "Local OTLP ingestion not visible"
            assert "12345678Z" not in json.dumps(data)
            assert "[DNI]" in json.dumps(data)
            supplied_costs = [
                {key: value for key, value in span["attributes"].items() if "cost" in key}
                for span in data
            ]
            # REST returns flat OpenInference attributes. Missing alias pricing
            # must not be interpreted as an actual cost of zero.
            assert any(cost.get("llm.cost.total") == 0.001 for cost in supplied_costs)
            selected_response = client.get(
                "/v1/projects/spike/spans",
                params={"attribute": "user.id:" + target},
            )
            selected_response.raise_for_status()
            selected = selected_response.json()["data"]
            assert len(selected) == 2
            trace_ids = {span["context"]["trace_id"] for span in selected}
            for trace_id in trace_ids:
                assert client.delete("/v1/traces/" + trace_id).status_code == 204
            remaining = client.get("/v1/projects/spike/spans").json()["data"]
            assert len(remaining) == 1
            assert not client.get(
                "/v1/projects/spike/spans",
                params={"attribute": "user.id:" + target},
            ).json()["data"]
            print(
                json.dumps(
                    {
                        "phoenix_image": IMAGE,
                        "unauthenticated_status": unauthorized,
                        "system_key_otlp_success": True,
                        "masked_spans_ingested": len(data),
                        "cost_observations": supplied_costs,
                        "span_response_keys": sorted(data[0]),
                        "user_filtered_traces_deleted": len(trace_ids),
                        "other_user_spans_preserved": len(remaining),
                        "storage": "disposable SQLite, not production PostgreSQL",
                    },
                    indent=2,
                )
            )
    finally:
        if provider is not None:
            provider.shutdown()
        docker("rm", "-f", name)


if __name__ == "__main__":
    main()
