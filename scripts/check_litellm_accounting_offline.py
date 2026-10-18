"""Offline accounting probe, run only in the pinned LiteLLM image via stdin.

No SDK inference invocation, server startup, real key, database, network or volume.
Exercises installed transformations/callback/budget code with synthetic responses
and in-memory substitutes at external I/O boundaries. Not a live certification.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import io
import json
import logging
import os
import socket
import sys
import unittest
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

VERSION = "1.100.1"
DIGEST = "sha256:a3715fa7ad8387941ab697259bd2881d68931657247a41984f90fae6d11c62bf"


def main() -> int:
    """Report only test names/counts and source hashes; never exception text."""
    network_attempts = []

    def no_network(*_args, **_kwargs):
        network_attempts.append(True)
        raise RuntimeError("offline_probe_network_forbidden")

    try:
        if importlib.metadata.version("litellm") != VERSION:
            raise RuntimeError("offline_probe_version_mismatch")
        if any(os.environ.get(k) for k in (
            "OPENROUTER_API_KEY", "OPENAI_API_KEY", "LITELLM_MASTER_KEY",
            "LITELLM_PROXY_VIRTUAL_KEY", "DATABASE_URL", "REDIS_URL",
        )):
            raise RuntimeError("offline_probe_requires_secret_free_container")
        os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "true"
        os.environ["LITELLM_LOG"] = "ERROR"
        logging.disable(sys.maxsize)
        with patch.object(socket.socket, "connect", no_network), patch.object(
            socket, "getaddrinfo", no_network,
        ):
            import httpx
            import litellm
            import litellm.proxy.proxy_server as proxy
            from litellm.cost_calculator import response_cost_calculator
            from litellm.llms.openrouter.chat.transformation import OpenrouterConfig
            from litellm.proxy._types import UserAPIKeyAuth
            from litellm.proxy.auth.auth_checks import _virtual_key_max_budget_check
            from litellm.proxy.db.db_spend_update_writer import DBSpendUpdateWriter
            from litellm.proxy.hooks.proxy_track_cost_callback import _ProxyDBLogger

            def transformed(cost, *, include_cost=True):
                usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
                if include_cost:
                    usage["cost"] = cost
                raw = {
                    "id": "synthetic", "object": "chat.completion", "created": 1,
                    "model": "gpt-6-luna", "choices": [{
                        "index": 0, "message": {"role": "assistant", "content": "synthetic"},
                        "finish_reason": "stop",
                    }], "usage": usage,
                }
                return OpenrouterConfig().transform_response(
                    model="gpt-6-luna", raw_response=httpx.Response(200, json=raw),
                    model_response=litellm.ModelResponse(), logging_obj=Mock(),
                    request_data={}, messages=[], optional_params={}, litellm_params={},
                    encoding=None,
                )

            def calculate(response):
                return response_cost_calculator(
                    response, model="openrouter/gpt-6-luna", custom_llm_provider="openrouter",
                    call_type="acompletion", optional_params={},
                )

            class AccountingProof(unittest.IsolatedAsyncioTestCase):
                def test_provider_cost_beats_missing_or_zero_local_pricing(self):
                    with patch.dict(litellm.model_cost, {}, clear=True):
                        self.assertEqual(calculate(transformed(0.03)), 0.03)
                    with patch.dict(litellm.model_cost, {
                        "openrouter/gpt-6-luna": {
                            "input_cost_per_token": 0, "output_cost_per_token": 0,
                            "litellm_provider": "openrouter", "mode": "chat",
                        },
                    }):
                        self.assertEqual(calculate(transformed(0.03)), 0.03)

                def test_metadata_zero_is_not_the_cost_of_a_response(self):
                    metadata = proxy._get_proxy_model_info({
                        "model_name": "synthetic-alias",
                        "litellm_params": {"model": "openrouter/gpt-6-luna"},
                        "model_info": {"input_cost_per_token": 0, "output_cost_per_token": 0},
                    })
                    self.assertEqual(metadata["model_info"]["input_cost_per_token"], 0)
                    self.assertEqual(calculate(transformed(0.03)), 0.03)

                def test_zero_provider_cost_is_honoured_not_repriced(self):
                    self.assertEqual(calculate(transformed(0.0)), 0.0)

                def test_missing_or_invalid_cost_has_no_positive_price_guarantee(self):
                    with patch.dict(litellm.model_cost, {}, clear=True):
                        for response in (transformed(None, include_cost=False),
                                         transformed("not-numeric")):
                            # The pinned library raises plain Exception for unknown pricing.
                            with self.assertRaises(Exception):  # noqa: B017
                                calculate(response)
                    # A negative upstream value is not rejected at this calculator boundary.
                    self.assertEqual(calculate(transformed(-0.01)), -0.01)

                async def test_real_callback_queues_key_spend_and_updates_counter(self):
                    cost = calculate(transformed(0.03))
                    writer = DBSpendUpdateWriter()
                    from litellm.caching.dual_cache import DualCache
                    cache = DualCache()
                    key_id = "synthetic-hash-not-a-real-token"
                    metadata = {"user_api_key": key_id, "user_api_key_user_id": "synthetic-user"}
                    kwargs = {"model": "ancoramind-default-r4", "call_type": "acompletion",
                              "litellm_params": {"metadata": metadata},
                              "response_cost": cost, "stream": False}

                    async def batch(**values):
                        await writer._update_key_db(
                            response_cost=values["response_cost"],
                            hashed_token=values["hashed_token"], prisma_client=object(),
                        )

                    logging_obj = SimpleNamespace(
                        db_spend_update_writer=writer, failed_tracking_alert=AsyncMock(),
                        slack_alerting_instance=SimpleNamespace(customer_spend_alert=AsyncMock()),
                    )
                    with ExitStack() as stack:
                        def replace(obj, name, value):
                            return stack.enter_context(patch.object(obj, name, value))
                        replace(proxy, "proxy_logging_obj", logging_obj)
                        replace(proxy, "general_settings", {})
                        replace(proxy, "prisma_client", object())
                        replace(proxy, "disable_spend_logs", True)
                        replace(proxy, "update_cache", AsyncMock())
                        replace(proxy, "user_api_key_cache", SimpleNamespace(
                            async_get_cache=AsyncMock(return_value=None),
                        ))
                        replace(proxy, "spend_counter_cache", cache)
                        replace(proxy, "_ensure_spend_counter_initialized", AsyncMock())
                        batch_call = replace(
                            writer, "_batch_database_updates", AsyncMock(side_effect=batch),
                        )
                        replace(writer, "_enqueue_tool_registry_upsert", Mock())
                        import litellm.proxy.spend_tracking.spend_tracking_utils as tracking
                        replace(tracking, "get_logging_payload", Mock(return_value={
                            "request_id": "synthetic-request", "startTime": "synthetic",
                            "endTime": "synthetic",
                        }))
                        await _ProxyDBLogger().async_log_success_event(
                            kwargs, transformed(0.03), datetime.now(UTC), datetime.now(UTC),
                        )
                        await asyncio.sleep(0)
                        batch_call.assert_awaited_once()
                        logging_obj.failed_tracking_alert.assert_not_called()
                        queued = writer.spend_update_queue.update_queue.get_nowait()
                        self.assertEqual(queued["response_cost"], cost)
                        self.assertEqual(queued["entity_id"], key_id)
                        self.assertEqual(cache.in_memory_cache.get_cache(
                            key="spend:key:" + key_id,
                        ), cost)
                        # Same real counter/budget reader, not an injected spend value.
                        token = UserAPIKeyAuth(token=key_id, max_budget=0.10, spend=0)
                        logger = SimpleNamespace(budget_alerts=AsyncMock())
                        await _virtual_key_max_budget_check(token, logger)
                        await proxy.increment_spend_counters(key_id, None, None, 0.08)
                        with self.assertRaises(litellm.BudgetExceededError):
                            await _virtual_key_max_budget_check(token, logger)
                        await asyncio.sleep(0)

                async def test_budget_blocks_at_or_above_limit_not_pre_reservation(self):
                    token = UserAPIKeyAuth(
                        token="synthetic-hash", max_budget=0.10, spend=0,  # noqa: S106
                    )
                    logger = SimpleNamespace(budget_alerts=AsyncMock())
                    for spend in (0.0, 0.09, 0.10, 0.12):
                        with patch.object(
                            proxy, "get_current_spend", AsyncMock(return_value=spend),
                        ):
                            if spend >= 0.10:
                                with self.assertRaises(litellm.BudgetExceededError):
                                    await _virtual_key_max_budget_check(token, logger)
                            else:
                                await _virtual_key_max_budget_check(token, logger)
                    await asyncio.sleep(0)

                async def test_missing_cost_reports_tracking_failure_not_budget_rejection(self):
                    logger = SimpleNamespace(failed_tracking_alert=AsyncMock())
                    import litellm.proxy.hooks.proxy_track_cost_callback as tracking
                    with (
                        patch.object(proxy, "proxy_logging_obj", logger),
                        patch.object(tracking, "_update_database_and_spend_counters",
                                     AsyncMock()) as update,
                    ):
                        await _ProxyDBLogger().async_log_success_event({
                            "model": "ancoramind-default-r4", "call_type": "acompletion",
                            "stream": False,
                            "litellm_params": {"metadata": {
                                "user_api_key": "synthetic-hash",
                                "user_api_key_user_id": "synthetic-user",
                            }},
                        }, transformed(None, include_cost=False), None, None)
                        await asyncio.sleep(0)
                        update.assert_not_awaited()
                        logger.failed_tracking_alert.assert_awaited_once()

                def test_disabling_spend_updates_skips_cost_tracking(self):
                    from litellm.proxy.hooks.proxy_track_cost_callback import (
                        _should_track_cost_callback,
                    )
                    for disabled in (False, True):
                        with patch.object(proxy, "general_settings", {
                            "disable_spend_updates": disabled,
                        }):
                            self.assertEqual(_should_track_cost_callback(
                                "synthetic-hash", None, None, None, "acompletion",
                            ), not disabled)

                async def test_unverified_spend_fails_closed_only_when_opted_in(self):
                    for strict in (False, True):
                        with (
                            patch.object(proxy, "general_settings", {
                                "fail_closed_budget_enforcement": strict,
                            }),
                            patch.object(proxy, "_read_spend_counter_estimate",
                                         AsyncMock(return_value=(0.0, False))),
                            patch.object(proxy, "_authoritative_floor_spend",
                                         AsyncMock(return_value=None)),
                        ):
                            if strict:
                                from fastapi import HTTPException
                                with self.assertRaises(HTTPException) as error:
                                    await proxy.get_current_spend("spend:key:synthetic", 0, 0.10)
                                self.assertEqual(error.exception.status_code, 503)
                            else:
                                self.assertEqual(await proxy.get_current_spend(
                                    "spend:key:synthetic", 0, 0.10,
                                ), 0)

                async def test_stale_counter_below_known_spend_is_repaired(self):
                    with (
                        patch.object(proxy, "general_settings", {}),
                        patch.object(proxy, "_read_spend_counter_estimate",
                                     AsyncMock(return_value=(0.01, True))),
                        patch.object(proxy, "_authoritative_floor_spend",
                                     AsyncMock(return_value=0.12)),
                        patch.object(proxy, "_repair_stale_spend_counter", AsyncMock()) as repair,
                    ):
                        self.assertEqual(await proxy.get_current_spend(
                            "spend:key:synthetic", 0.10, 0.10,
                        ), 0.12)
                        repair.assert_awaited_once()

            result = unittest.TextTestRunner(stream=io.StringIO()).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(AccountingProof),
            )
            root = Path(importlib.metadata.distribution("litellm").locate_file("litellm"))
            sources = ["llms/openrouter/chat/transformation.py", "cost_calculator.py",
                       "proxy/hooks/proxy_track_cost_callback.py", "proxy/auth/auth_checks.py",
                       "proxy/proxy_server.py", "proxy/db/db_spend_update_writer.py"]
            report = {
                "status": "offline_accounting_verified" if result.wasSuccessful()
                and not network_attempts else "offline_accounting_failed",
                "litellm_version": VERSION, "expected_image_digest": DIGEST,
                "tests_run": result.testsRun,
                "failed_tests": [test.id().split(".")[-1]
                                 for test, _ in result.failures + result.errors],
                "network_attempts": len(network_attempts), "inference_started": False,
                "live_spend_verified": False, "campaign_approved": False,
                "source_sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                                  for name in sources},
            }
            print(json.dumps(report))
            return 0 if report["status"] == "offline_accounting_verified" else 1
    except Exception:
        print(json.dumps({"status": "offline_accounting_blocked", "inference_started": False,
                          "network_attempts": len(network_attempts)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
