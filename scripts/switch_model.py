"""One-command physical model switch: publish, grant, verify, activate (ADR-005).

Wraps the exact same approved steps as ``litellm_gateway_alias.py`` and
``runtime_config.py`` — same ``/model/*`` Gateway routes, same versioned-alias
rule (never edit or retire the alias in use), same CAS-protected runtime-config
revision — so this adds no new write path, it only removes the manual toil of
running five separate commands and copying JSON/revision numbers by hand
between them.

Must run from inside the AncoraMind app's own Railway container (``railway
ssh <servicio>`` or the dashboard Shell): the Gateway admin port is only
reachable on Railway's private network, and the app's admin API can be
reached at ``http://localhost:$PORT`` from there without a public URL.

Usage (bash, inside the Railway container):
  export LITELLM_PROXY_ADMIN_URL='http://litellm.railway.internal:4000'
  export LITELLM_MASTER_KEY='sk-master'
  export LITELLM_PROXY_VIRTUAL_KEY='sk-ancoramind'
  export RUNTIME_CONFIG_ADMIN_TOKEN='<token>'
  export RUNTIME_CONFIG_ADMIN_ACTOR='jesus'

  python scripts/switch_model.py \\
    --route ancoramind-default \\
    --model openrouter/gpt-6-luna \\
    --input-cost 0.10 --output-cost 0.50 \\
    --base-config specs/013-llm-access-governance/configs/ancoramind-default-r2.json \\
    --app-base-url http://localhost:$PORT \\
    --reason "Probar GPT-6 Luna tras EmptyAgentResponse con GLM-5.3 Flash" \\
    --smoke

Add ``--dry-run`` to see every computed value (next alias, patched config,
revision numbers) without publishing, granting or activating anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))

import litellm_gateway_alias as gw  # noqa: E402
import runtime_config as rc  # noqa: E402

CONFIGS_DIR = PROJECT_ROOT / "specs" / "013-llm-access-governance" / "configs"


class SwitchModelError(RuntimeError):
    """Operator-facing failure that carries no secret material."""


def next_alias(route: str, published: list[str]) -> str:
    """Return ``<route>-r<N+1>`` from the highest published version for this route."""
    prefix = f"{route}-r"
    versions = [
        int(name[len(prefix) :])
        for name in published
        if name.startswith(prefix) and name[len(prefix) :].isdigit()
    ]
    return f"{prefix}{max(versions, default=1) + 1}"


def patch_config(base_config: dict[str, Any], *, route: str, alias: str) -> dict[str, Any]:
    """Point one logical route at the new alias and prune pricing for the old one."""
    patched: dict[str, Any] = json.loads(json.dumps(base_config))  # deep copy, no extra deps
    routes = patched.get("routing", {}).get("routes", {})
    if route not in routes:
        raise SwitchModelError(f"Base config has no route {route!r} to patch")
    routes[route]["effective_gateway_route"] = alias
    effective_aliases = {entry["effective_gateway_route"] for entry in routes.values()}
    pricing_routes = patched.get("pricing", {}).get("routes", {})
    for stale in list(pricing_routes):
        if stale not in effective_aliases:
            del pricing_routes[stale]
    return patched


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--route", required=True, help="Logical route, e.g. ancoramind-default")
    parser.add_argument("--model", required=True, help="e.g. openrouter/gpt-6-luna")
    parser.add_argument("--input-cost", required=True, type=float, help="USD per 1M input tokens")
    parser.add_argument(
        "--output-cost", required=True, type=float, help="USD per 1M output tokens"
    )
    parser.add_argument(
        "--base-config", required=True, help="Full runtime config JSON to patch from"
    )
    parser.add_argument("--app-base-url", required=True, help="AncoraMind app admin base URL")
    parser.add_argument("--reason", required=True, help="Audit reason")
    parser.add_argument("--alias", help="Override the auto-computed <route>-r<N+1> alias")
    parser.add_argument("--rpm", type=int, default=gw.DEFAULT_RPM)
    parser.add_argument("--tpm", type=int, default=gw.DEFAULT_TPM)
    parser.add_argument("--out", help="Where to write the patched candidate (default: configs/)")
    parser.add_argument(
        "--smoke", action="store_true", help="Send one real completion through the new alias"
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute and print, change nothing")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        env = __import__("os").environ
        gw_base_url = gw._admin_base_url(env)
        gw_master_key = gw._master_key(env)
        gw_virtual_key = gw._virtual_key(env)
        settings = rc._settings()
        admin_token = rc._admin_token(settings)
        admin_actor = rc._admin_actor()

        published = gw.published_aliases(gw_base_url, gw_master_key)
        alias = args.alias or next_alias(str(args.route), published)
        gw.validate_alias(alias)
        print(f"Next alias for {args.route}: {alias} -> {args.model}")

        base_config = rc._load_json_file(str(args.base_config))
        patched = patch_config(base_config, route=str(args.route), alias=alias)
        pricing_routes = patched.setdefault("pricing", {}).setdefault("routes", {})
        pricing_routes[alias] = {
            "input_cost_per_1m_usd": args.input_cost,
            "output_cost_per_1m_usd": args.output_cost,
        }
        out_path = Path(args.out) if args.out else CONFIGS_DIR / f"{alias}.json"

        if args.dry_run:
            print(json.dumps(patched, indent=2, ensure_ascii=False))
            print(f"Would write candidate to {out_path}")
            print("Dry run: no publish, grant, smoke, validate, create-revision or activate.")
            return 0

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(patched, indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote candidate config to {out_path}")

        if alias in published:
            print(f"Alias {alias} already published; skipping publish")
        else:
            payload = gw.build_model_payload(
                alias=alias, model=str(args.model), rpm=args.rpm, tpm=args.tpm
            )
            gw._request(
                "POST", f"{gw_base_url}/model/new", master_key=gw_master_key, json_body=payload
            )
            print(f"Published {alias} -> {args.model}")

        current_grants = gw.key_allowlist(gw_base_url, gw_master_key, gw_virtual_key)
        merged = gw.merge_alias_allowlist(current_grants, [alias])
        gw._request(
            "POST",
            f"{gw_base_url}/key/update",
            master_key=gw_master_key,
            json_body={"key": gw_virtual_key, "models": merged},
        )
        print(f"Granted to the virtual key: {', '.join(merged)}")

        if args.smoke:
            gw.smoke_inference(gw_base_url, gw_virtual_key, alias)
            print(f"Smoke inference OK for {alias}")

        status_code, text = rc._request(
            base_url=str(args.app_base_url),
            method="POST",
            path="/admin/runtime-config/validate",
            token=admin_token,
            actor=admin_actor,
            payload={"config": patched},
        )
        if not (200 <= status_code < 300):
            raise SwitchModelError(f"Validation failed: HTTP {status_code} {text}")
        result = json.loads(text)
        if not result.get("valid"):
            raise SwitchModelError("Validation failed: " + json.dumps(result.get("errors")))
        print("Candidate config is valid.")

        status_code, text = rc._request(
            base_url=str(args.app_base_url),
            method="GET",
            path="/admin/runtime-config/status",
            token=admin_token,
            actor=admin_actor,
        )
        if not (200 <= status_code < 300):
            raise SwitchModelError(f"status failed: HTTP {status_code} {text}")
        current_revision = int(json.loads(text)["active_revision"])
        print(f"Current active revision: {current_revision}")

        status_code, text = rc._request(
            base_url=str(args.app_base_url),
            method="POST",
            path="/admin/runtime-config/revisions",
            token=admin_token,
            actor=admin_actor,
            payload={"config": patched, "reason": str(args.reason)},
        )
        if not (200 <= status_code < 300):
            raise SwitchModelError(f"create-revision failed: HTTP {status_code} {text}")
        new_revision = int(json.loads(text)["revision"])
        print(f"Created revision {new_revision}")

        status_code, text = rc._request(
            base_url=str(args.app_base_url),
            method="POST",
            path=f"/admin/runtime-config/revisions/{new_revision}/activate",
            token=admin_token,
            actor=admin_actor,
            payload={"expected_current_revision": current_revision, "reason": str(args.reason)},
        )
        if not (200 <= status_code < 300):
            raise SwitchModelError(f"activate failed: HTTP {status_code} {text}")
        print(f"HTTP {status_code}")
        print(json.dumps(json.loads(text), indent=2, ensure_ascii=False))
        print(
            f"\nDone: {args.route} now routes to {alias} ({args.model}). "
            f"Rollback: activate revision {current_revision} again "
            f"(--expected-current-revision {new_revision})."
        )
        return 0
    except (gw.AliasError, SwitchModelError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
