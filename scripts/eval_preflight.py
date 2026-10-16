"""Validate an isolated eval plan; optional GET /models, never paid inference."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.eval_campaign import (  # noqa: E402
    EvalCampaignPlan,
    gateway_settings,
    verify_gateway_models,
)
from src.domain.runtime_config.models import RuntimeConfigSnapshot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--check-gateway", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.snapshot.is_absolute() or not args.plan.is_absolute():
            raise ValueError("eval_absolute_paths_required")
        snapshot = RuntimeConfigSnapshot.model_validate_json(
            args.snapshot.read_text(encoding="utf-8")
        )
        plan = EvalCampaignPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
        plan.validate_snapshot(snapshot)
        metadata = plan.metadata()
        metadata["inference_started"] = False
        metadata["gateway_access"] = "not_checked"
        metadata["approval_status"] = "pending_separate_approval"
        if args.check_gateway:
            settings = gateway_settings(os.environ)
            with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
                response = client.get(
                    settings.litellm_proxy_base_url.rstrip("/") + "/models",
                    headers={"Authorization": "Bearer " + settings.litellm_proxy_virtual_key},
                )
                if response.status_code != 200:
                    raise ValueError("eval_gateway_auth_failed")
                verify_gateway_models(response.json(), plan.effective_gateway_route)
            metadata["gateway_access"] = "restricted_alias_verified"
        print(json.dumps({"status": "valid", **metadata}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, ValidationError, httpx.HTTPError, KeyError, TypeError):
        # Neither Pydantic inputs nor provider/HTTP exception text are safe logs.
        print(json.dumps({"status": "blocked", "code": "eval_preflight_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
