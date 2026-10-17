"""Paste into the approved eval shell: read-only checks, no key persistence.

The temporary key is entered with getpass through /dev/tty, not in source/history.
Requires the existing, approved /app image; this operator helper is not deployed.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import sys
import warnings
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path("/app")
SHA = "db0c59be0b2eeb807d4222aeb5a62b622d90b200"
SOURCE = "108c410d26149cd5e3946e15d16f728fdfbdd4f6a8553fef1ec787df271e6c82"
PLAN = "8f3e4a51496dbbdc763fd17458e8857fe785bd8abaf6016881effe6f79bd8139"
ROUTES = {"/models", "/v1/models", "/key/info"}


def verified_info(info: dict, now: datetime) -> dict:
    expires = datetime.fromisoformat(info["expires"].replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if (
        info.get("models") != ["ancoramind-default-r4"]
        or set(info.get("allowed_routes") or []) != ROUTES
        or Decimal(str(info.get("max_budget"))) != Decimal("0.10")
        or Decimal(str(info.get("spend"))) != 0
        or info.get("budget_duration") is not None or info.get("budget_reset_at") is not None
        or info.get("max_parallel_requests") != 1
        or info.get("rpm_limit") != 30 or info.get("tpm_limit") != 250000
        or info.get("blocked") or info.get("auto_rotate")
        or not now < expires <= now + timedelta(hours=2, minutes=2)
        or not str(info.get("key_alias", "")).startswith("ancoramind-evals-access-")
    ):
        raise ValueError("eval_gateway_key_restrictions_mismatch")
    for name in ("aliases", "config", "permissions"):
        value = info.get(name)
        if isinstance(value, str):
            value = json.loads(value)
        if value is not None and value != {}:
            raise ValueError("eval_gateway_key_overrides_forbidden")
    return {"key_alias": info["key_alias"], "expires": expires.isoformat(),
            "max_budget_usd": "0.10", "spend_usd": "0", "budget_reset": False}


def main() -> int:
    disabled = logging.root.manager.disable
    stage = "imports"
    http_status = None
    gateway_url_present = bool(os.environ.get("ANCORA_EVAL_GATEWAY_URL", "").strip())
    try:
        logging.disable(sys.maxsize)
        sys.path.insert(0, str(ROOT))
        import httpx

        from scripts.eval_source import source_identity
        from src.agent.eval_campaign import (
            EvalCampaignPlan,
            gateway_settings,
            verify_gateway_models,
        )
        from src.domain.runtime_config.models import RuntimeConfigSnapshot

        stage = "source_identity"
        identity = source_identity(ROOT)
        if (identity.get("code_sha"), identity.get("source_fingerprint"),
            identity.get("identity_source")) != (SHA, SOURCE, "sealed_image"):
            raise ValueError("eval_candidate_mismatch")
        stage = "plan_snapshot"
        folder = ROOT / "evals" / "response_style"
        plan = EvalCampaignPlan.model_validate_json(
            (folder / "bl48-campaign-plan.json").read_text()
        )
        snapshot = RuntimeConfigSnapshot.model_validate_json(
            (folder / "runtime-rev8-snapshot.json").read_text()
        )
        plan.validate_snapshot(snapshot)
        if plan.checksum() != PLAN:
            raise ValueError("eval_plan_mismatch")
        stage = "private_console"
        with (
            open("/dev/tty", "w", encoding="utf-8") as console,
            warnings.catch_warnings(),
        ):
            if not console.isatty():
                raise ValueError("eval_private_tty_required")
            warnings.simplefilter("error", getpass.GetPassWarning)
            stage = "key_input"
            key = getpass.getpass("Clave eval temporal (entrada oculta, NO master key): ",
                                 stream=console)
        stage = "gateway_settings"
        settings = gateway_settings({
            "ANCORA_EVAL_GATEWAY_URL": os.environ.get("ANCORA_EVAL_GATEWAY_URL", ""),
            "ANCORA_EVAL_GATEWAY_KEY": key,
        })
        stage = "http_client"
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            headers = {"Authorization": "Bearer " + settings.litellm_proxy_virtual_key}
            stage = "models_request"
            models = client.get(settings.litellm_proxy_base_url + "/models", headers=headers)
            http_status = models.status_code
            stage = "models_response"
            models.raise_for_status()
            stage = "models_scope"
            verify_gateway_models(models.json(), plan.effective_gateway_route)
            stage = "key_info_request"
            http_status = None
            response = client.get(
                settings.litellm_proxy_base_url.removesuffix("/v1") + "/key/info",
                headers=headers,
            )
            http_status = response.status_code
            stage = "key_info_response"
            response.raise_for_status()
            stage = "key_info_restrictions"
            metadata = verified_info(response.json()["info"], datetime.now(UTC))
        print(json.dumps({
            "status": "eval_gateway_read_only_verified", **metadata,
            "gateway_access": "restricted_alias_verified", "models": [plan.effective_gateway_route],
            "code_sha": SHA, "source_fingerprint": SOURCE, "plan_checksum": PLAN,
            "inference_enabled": False, "inference_started": False,
            "pricing_verified": False, "approval_status": "pending_separate_approval",
        }))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        # Fixed vocabulary only; no exception text, URL, response body or traceback.
        name = type(error).__name__
        error_class = name if name in {
            "ValueError", "KeyError", "TypeError", "AttributeError", "OSError",
            "FileNotFoundError", "PermissionError", "ModuleNotFoundError", "ImportError",
            "JSONDecodeError", "ValidationError", "InvalidOperation", "GetPassWarning",
            "KeyboardInterrupt", "EOFError", "HTTPStatusError", "ConnectError",
            "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout",
            "RemoteProtocolError", "LocalProtocolError", "UnsupportedProtocol", "InvalidURL",
        } else "OtherError"
        print(json.dumps({
            "status": "eval_gateway_check_blocked", "stage": stage, "error_class": error_class,
            "http_status": http_status, "gateway_url_present": gateway_url_present,
            "inference_started": False,
        }))
        return 1
    finally:
        logging.disable(disabled)


if __name__ == "__main__":
    raise SystemExit(main())
