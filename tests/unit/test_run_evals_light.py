"""Coste real que informa OpenRouter en el runner de evals ligero (spec 049)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from scripts import judge_bench, report_evals
from scripts import run_evals_light as light
from src.agent import governed_model
from src.agent.evals import load_eval_cases
from src.domain.llm_access.models import LlmUsageEventCreate


def _event(status: str = "completed", inp: int = 100, out: int = 10) -> LlmUsageEventCreate:
    return LlmUsageEventCreate(
        interaction_id=uuid4(), llm_call_id=uuid4(), config_revision=1,
        logical_route="r", effective_gateway_route="r", input_tokens=inp,
        output_tokens=out, estimated_cost=0.0, status=status)


def _response(cost: object) -> SimpleNamespace:
    return SimpleNamespace(response_usage=SimpleNamespace(cost=cost))


@pytest.mark.parametrize(("value", "expected"), [
    (0.000914, 0.000914), (0, 0.0), (2, 2.0),
    (None, None), ("0.1", None), (True, None), (-0.5, None)])
def test_reported_cost_accepts_only_valid_amounts(value: object, expected: float | None):
    assert judge_bench.reported_cost(value) == expected


def _judge_client(usage: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answers": {"cumple": {"noul": 0.9}}, "usage": usage})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ask_with_cost_returns_the_provider_amount():
    client = _judge_client({"input_tokens": 177, "cost": 1.77e-06})

    p, tokens, cost = judge_bench.ask_with_cost(client, "k", "respan/span-02", {
        "state": {}, "criterion": "c"})

    assert (p, tokens, cost) == (0.9, 177, 1.77e-06)


def test_ask_keeps_its_original_contract_and_cost_is_none_when_absent():
    client = _judge_client({"input_tokens": 50})

    assert judge_bench.ask(client, "k", "respan/span-02", {"state": {}, "criterion": "c"}) == (
        0.9, 50)
    assert judge_bench.ask_with_cost(client, "k", "respan/span-02", {
        "state": {}, "criterion": "c"})[2] is None


def test_judge_case_sums_provider_costs_and_flags_a_missing_one():
    case = next(c for c in load_eval_cases() if c.response_criteria)
    expected_calls = len(case.response_criteria)
    with _judge_client({"input_tokens": 10, "cost": 0.5}) as client:
        verdicts, tokens, cost = light.judge_case(client, "k", case, "a", "", "m")
    assert len(verdicts) == expected_calls
    assert tokens == 10 * expected_calls
    assert cost == pytest.approx(0.5 * expected_calls)

    with _judge_client({"input_tokens": 10}) as client:
        _verdicts, _tokens, cost = light.judge_case(client, "k", case, "a", "", "m")
    assert cost is None


def test_take_sums_the_provider_cost_of_completed_calls():
    collector = light.UsageCollector()
    collector.events += [_event(), _event()]
    collector.record_provider_cost(_response(0.000914))
    collector.record_provider_cost(_response(0.000117))

    usage = collector.take()

    assert usage["provider_cost_usd"] == pytest.approx(0.001031)
    assert usage["model_calls"] == 2
    assert collector.provider_costs == [] and collector.events == []


def test_take_reports_none_when_a_completed_call_has_no_cost():
    collector = light.UsageCollector()
    collector.events += [_event(), _event()]
    collector.record_provider_cost(_response(0.001))
    collector.record_provider_cost(_response(None))
    assert collector.take()["provider_cost_usd"] is None

    # Una completada sin ninguna lectura de coste tampoco se da por conocida.
    collector.events += [_event()]
    assert collector.take()["provider_cost_usd"] is None


def test_take_ignores_failed_calls_that_never_returned_a_response():
    collector = light.UsageCollector()
    collector.events += [_event(), _event(status="error")]
    collector.record_provider_cost(_response(0.002))

    assert collector.take()["provider_cost_usd"] == pytest.approx(0.002)


def test_agent_cost_prefers_the_provider_amount_and_falls_back_to_the_estimate():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert light.agent_cost({**usage, "provider_cost_usd": 0.07}) == 0.07
    assert light.agent_cost({**usage, "provider_cost_usd": 0.0}) == 0.0
    assert light.agent_cost({**usage, "provider_cost_usd": None}) == pytest.approx(0.10)
    assert light.agent_cost(usage) == pytest.approx(0.10)


def test_cost_probe_records_the_cost_and_does_not_change_the_result(monkeypatch):
    monkeypatch.setattr(governed_model, "_actual_call_cost", lambda *_: 0.5)
    monkeypatch.delattr(governed_model, "_actual_call_cost_original", raising=False)
    collector = light.UsageCollector()

    light.install_cost_probe(collector)
    result = governed_model._actual_call_cost(None, "route", _response(0.000914))

    assert result == 0.5
    assert collector.provider_costs == [0.000914]
    # Reinstalar no apila sondas: cada llamada se registra una sola vez.
    light.install_cost_probe(collector)
    governed_model._actual_call_cost(None, "route", _response(0.1))
    assert collector.provider_costs == [0.000914, 0.1]
    monkeypatch.delattr(governed_model, "_actual_call_cost_original", raising=False)


def test_disable_telemetry_sets_the_flag_but_respects_an_operator_value(monkeypatch):
    # setenv antes de delenv: así monkeypatch restaura "ausente" y no filtra el valor.
    monkeypatch.setenv("OTEL_SDK_DISABLED", "placeholder")
    monkeypatch.delenv("OTEL_SDK_DISABLED")
    light.disable_telemetry()
    assert light.os.environ["OTEL_SDK_DISABLED"] == "true"

    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    light.disable_telemetry()
    assert light.os.environ["OTEL_SDK_DISABLED"] == "false"


def test_report_shows_the_real_cost_and_marks_estimates():
    real = {"agent_cost_usd": 0.0123, "agent_cost_est_usd": 0.09,
            "judge_cost_usd": 0.0002, "judge_cost_est_usd": 0.0003}
    assert report_evals.cost_label(real) == "0.0123+0.0002 USD"

    missing = {"agent_cost_usd": None, "agent_cost_est_usd": 0.09,
               "judge_cost_usd": None, "judge_cost_est_usd": 0.0003}
    assert report_evals.cost_label(missing) == "~0.09+~0.0003 USD"

    legacy = {"agent_cost_usd": None, "agent_cost_est_usd": 0.0926, "judge_cost_usd": 0.0002}
    assert report_evals.cost_label(legacy) == "~0.0926+~0.0002 USD"
