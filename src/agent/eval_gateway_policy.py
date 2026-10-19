"""Read-only validation of a dedicated eval key; never create or reset budgets."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from src.agent.eval_campaign import EvalCampaignPlan


def validate_key_info(info: dict[str, Any], plan: EvalCampaignPlan, *, required: Decimal,
                      maximum: Decimal = Decimal(1)) -> None:
    expires = datetime.fromisoformat(info["expires"].replace("Z", "+00:00"))
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    try:
        spend, ceiling = Decimal(str(info["spend"])), Decimal(str(info["max_budget"]))
    except Exception:
        raise ValueError("eval_reusable_key_scope_budget_or_expiry_invalid") from None
    allowed = {"/models", "/v1/models", "/key/info", "/chat/completions", "/v1/chat/completions"}
    if (info.get("models") != [plan.effective_gateway_route]
        or not str(info.get("key_alias", "")).startswith("ancoramind-evals-")
        or not spend.is_finite() or not ceiling.is_finite() or spend < 0
        or ceiling <= 0 or ceiling > maximum or spend > ceiling or ceiling - spend < required
        or type(info.get("max_parallel_requests")) is not int
        or info.get("max_parallel_requests") != 1 or info.get("budget_duration") is not None
        or info.get("budget_reset_at") is not None
        or info.get("blocked") or info.get("auto_rotate") or not datetime.now(UTC) < expires
        or not set(info.get("allowed_routes") or []) <= allowed
        or not {"/v1/chat/completions", "/key/info"} <= set(info.get("allowed_routes") or [])):
        raise ValueError("eval_reusable_key_scope_budget_or_expiry_invalid")
    for name in ("aliases", "config", "permissions"):
        value = info.get(name)
        if isinstance(value, str):
            value = json.loads(value)
        if value is not None and value != {}:
            raise ValueError("eval_reusable_key_overrides_forbidden")
