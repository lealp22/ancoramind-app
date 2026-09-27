"""Publish, grant, verify and retire versioned LiteLLM Gateway aliases (ADR-005).

A physical model change never edits an existing alias: it publishes a new
versioned alias (``r2``, ``r3``, ...) and a runtime-config revision then points
to it. The Gateway must run with ``store_model_in_db: true``.

Usage (PowerShell), against the private Railway service:
  $env:LITELLM_PROXY_ADMIN_URL='http://litellm.railway.internal:4000'
  $env:LITELLM_MASTER_KEY='sk-master'
  python scripts/litellm_gateway_alias.py verify

  python scripts/litellm_gateway_alias.py publish `
    --alias ancoramind-default-r3 --model openrouter/gpt-6-luna

  $env:LITELLM_PROXY_VIRTUAL_KEY='sk-ancoramind'
  python scripts/litellm_gateway_alias.py grant --alias ancoramind-default-r2

  python scripts/litellm_gateway_alias.py verify --alias ancoramind-default-r2 --smoke
  python scripts/litellm_gateway_alias.py retire --alias ancoramind-default-r2

The master key is an operator secret: it is never printed, logged or persisted,
and AncoraMind itself only ever holds the restricted virtual key. Only the
``/model/*`` management routes are used; writing settings through the API would
silently overlay ``gateway/litellm-config.yaml`` at the next startup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.runtime_config.models import GATEWAY_ROUTE_PATTERN  # noqa: E402

DEFAULT_RPM = 60
DEFAULT_TPM = 250_000
API_KEY_ENV_REFERENCE = "os.environ/OPENROUTER_API_KEY"


class AliasError(RuntimeError):
    """Operator-facing failure that carries no secret material."""


def validate_alias(alias: str) -> str:
    """Reject anything that is not a versioned ``<name>-r<N>`` Gateway alias."""
    if not GATEWAY_ROUTE_PATTERN.fullmatch(alias):
        raise AliasError(
            f"{alias!r} is not a versioned Gateway alias (expected <name>-r<N>, e.g. "
            "ancoramind-default-r2)"
        )
    return alias


def build_model_payload(
    *,
    alias: str,
    model: str,
    rpm: int = DEFAULT_RPM,
    tpm: int = DEFAULT_TPM,
) -> dict[str, Any]:
    """Render the ``POST /model/new`` body, mirroring the base alias shape."""
    validate_alias(alias)
    if not model.strip():
        raise AliasError("model must not be blank")
    if rpm <= 0 or tpm <= 0:
        raise AliasError("rpm and tpm must be positive integers")
    return {
        "model_name": alias,
        "litellm_params": {
            "model": model.strip(),
            "api_key": API_KEY_ENV_REFERENCE,
        },
        "model_info": {"rpm": rpm, "tpm": tpm},
    }


def merge_alias_allowlist(
    current: Sequence[str],
    additional: Sequence[str],
) -> list[str]:
    """Return an additive, de-duplicated allowlist preserving the current order.

    Additive on purpose: rolling back to a previously granted alias must not
    depend on touching the virtual key again.
    """
    merged = list(dict.fromkeys(current))
    for alias in additional:
        validate_alias(alias)
        if alias not in merged:
            merged.append(alias)
    return merged


def remove_from_allowlist(current: Sequence[str], retired: Sequence[str]) -> list[str]:
    """Drop the retired aliases while preserving the remaining order."""
    drop = set(retired)
    return [alias for alias in current if alias not in drop]


def is_base_alias(alias: str) -> bool:
    """Base aliases are declared in Git and must never be published or retired here."""
    return alias.endswith("-r1")


def _admin_base_url(env: Mapping[str, str]) -> str:
    base_url = env.get("LITELLM_PROXY_ADMIN_URL", "").strip().rstrip("/")
    if not base_url:
        raise AliasError("LITELLM_PROXY_ADMIN_URL is required")
    return base_url


def _master_key(env: Mapping[str, str]) -> str:
    master_key = env.get("LITELLM_MASTER_KEY", "").strip()
    if not master_key:
        raise AliasError("LITELLM_MASTER_KEY is required")
    return master_key


def _virtual_key(env: Mapping[str, str]) -> str:
    virtual_key = env.get("LITELLM_PROXY_VIRTUAL_KEY", "").strip()
    if not virtual_key:
        raise AliasError("LITELLM_PROXY_VIRTUAL_KEY is required for grant/retire/--smoke")
    return virtual_key


def _request(
    method: str,
    url: str,
    *,
    master_key: str,
    json_body: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> Any:
    """Call an admin route, surfacing only a status code and a truncated body."""
    try:
        response = httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {master_key}"},
            json=json_body,
            params=params,
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise AliasError(f"LiteLLM admin request failed: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        detail = " ".join(response.text.split())[:200]
        raise AliasError(f"LiteLLM admin request failed: HTTP {response.status_code} {detail}")
    try:
        return response.json()
    except ValueError:
        return {}


def _model_entries(base_url: str, master_key: str) -> list[dict[str, Any]]:
    payload = _request("GET", f"{base_url}/model/info", master_key=master_key)
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def published_aliases(base_url: str, master_key: str) -> list[str]:
    """Return the sorted public model names currently served by the Gateway."""
    names = {str(item.get("model_name")) for item in _model_entries(base_url, master_key)}
    return sorted(name for name in names if name and name != "None")


def model_ids_for_alias(base_url: str, master_key: str, alias: str) -> list[str]:
    """Return every stored deployment id backing an alias (``/model/delete`` ids).

    LiteLLM keeps only ``model_name``, ``litellm_params`` and ``model_info`` at
    the top level of ``/model/info``; the deletable id is nested as
    ``model_info.id``.
    """
    ids: list[str] = []
    for item in _model_entries(base_url, master_key):
        if str(item.get("model_name")) != alias:
            continue
        model_info = item.get("model_info")
        nested_id = model_info.get("id") if isinstance(model_info, dict) else None
        model_id = nested_id or item.get("model_id") or item.get("id")
        if model_id:
            ids.append(str(model_id))
    return ids


def db_model_aliases(base_url: str, master_key: str) -> list[str]:
    """Return the aliases stored in the Gateway database (published at runtime).

    Aliases absent from this list are the ``r1`` base declared in
    ``gateway/litellm-config.yaml`` and owned by that file.
    """
    names = {
        str(item.get("model_name"))
        for item in _model_entries(base_url, master_key)
        if isinstance(item.get("model_info"), dict) and item["model_info"].get("db_model")
    }
    return sorted(name for name in names if name and name != "None")


def key_allowlist(base_url: str, master_key: str, virtual_key: str) -> list[str]:
    """Read the alias allowlist currently granted to the AncoraMind virtual key."""
    payload = _request(
        "GET",
        f"{base_url}/key/info",
        master_key=master_key,
        params={"key": virtual_key},
    )
    info = payload.get("info") if isinstance(payload, dict) else None
    models = info.get("models") if isinstance(info, dict) else None
    if not isinstance(models, list):
        return []
    return [str(model) for model in models]


def smoke_inference(base_url: str, virtual_key: str, alias: str) -> None:
    """Send one real completion through the alias; only used by ``verify --smoke``."""
    try:
        response = httpx.post(
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {virtual_key}"},
            json={
                "model": alias,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=60.0,
        )
    except httpx.HTTPError as exc:
        raise AliasError(f"Smoke inference failed: {type(exc).__name__}") from exc
    if response.status_code >= 400:
        detail = " ".join(response.text.split())[:200]
        raise AliasError(f"Smoke inference failed: HTTP {response.status_code} {detail}")


def command_publish(args: argparse.Namespace, env: Mapping[str, str], *, dry_run: bool) -> int:
    """Publish one new versioned alias with the audited per-route ceilings."""
    alias = validate_alias(str(args.alias))
    if is_base_alias(alias) and not args.allow_base:
        raise AliasError(
            f"{alias} is a base alias declared in gateway/litellm-config.yaml; publish a new "
            "versioned alias instead (or pass --allow-base to override)"
        )
    payload = build_model_payload(
        alias=alias,
        model=str(args.model),
        rpm=int(args.rpm),
        tpm=int(args.tpm),
    )
    if dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    base_url = _admin_base_url(env)
    master_key = _master_key(env)
    if alias in published_aliases(base_url, master_key) and not args.force:
        print(f"Alias {alias} is already published; nothing to do (use --force to add it again)")
        return 0
    _request("POST", f"{base_url}/model/new", master_key=master_key, json_body=payload)
    print(f"Published {alias} -> {payload['litellm_params']['model']}")
    return 0


def command_grant(args: argparse.Namespace, env: Mapping[str, str], *, dry_run: bool) -> int:
    """Add aliases to the AncoraMind virtual key without dropping the current ones."""
    aliases = [validate_alias(str(alias)) for alias in args.alias]
    base_url = _admin_base_url(env)
    master_key = _master_key(env)
    virtual_key = _virtual_key(env)
    current = key_allowlist(base_url, master_key, virtual_key)
    merged = merge_alias_allowlist(current, aliases)
    if dry_run:
        print(json.dumps({"models": merged}, indent=2, ensure_ascii=False))
        return 0
    _request(
        "POST",
        f"{base_url}/key/update",
        master_key=master_key,
        json_body={"key": virtual_key, "models": merged},
    )
    print("Granted to the virtual key: " + ", ".join(merged))
    return 0


def command_verify(args: argparse.Namespace, env: Mapping[str, str], *, dry_run: bool) -> int:
    """Confirm that the expected aliases are published and usable."""
    base_url = _admin_base_url(env)
    master_key = _master_key(env)
    published = published_aliases(base_url, master_key)
    runtime_published = db_model_aliases(base_url, master_key)
    print(
        json.dumps(
            {
                "published_aliases": published,
                "runtime_published_aliases": runtime_published,
                "base_aliases_from_git": [
                    alias for alias in published if alias not in runtime_published
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    expected = [validate_alias(str(alias)) for alias in (args.alias or [])]
    missing = [alias for alias in expected if alias not in published]
    if missing:
        raise AliasError("Alias not published in the Gateway: " + ", ".join(missing))
    if not args.smoke:
        return 0
    virtual_key = _virtual_key(env)
    if dry_run:
        print(f"Would run one smoke inference for: {', '.join(expected)}")
        return 0
    for alias in expected or published:
        smoke_inference(base_url, virtual_key, alias)
        print(f"Smoke inference OK for {alias}")
    return 0


def command_retire(args: argparse.Namespace, env: Mapping[str, str], *, dry_run: bool) -> int:
    """Remove an alias from the virtual key and delete its stored definitions."""
    aliases = [validate_alias(str(alias)) for alias in args.alias]
    base = [alias for alias in aliases if is_base_alias(alias)]
    if base and not args.allow_base:
        raise AliasError(
            "Refusing to retire base aliases declared in Git: "
            + ", ".join(base)
            + " (pass --allow-base to override)"
        )
    base_url = _admin_base_url(env)
    master_key = _master_key(env)
    virtual_key = _virtual_key(env)
    remaining = remove_from_allowlist(key_allowlist(base_url, master_key, virtual_key), aliases)
    targets = {alias: model_ids_for_alias(base_url, master_key, alias) for alias in aliases}
    if dry_run:
        preview = {"models": remaining, "delete_ids": targets}
        print(json.dumps(preview, indent=2, ensure_ascii=False))
        return 0
    _request(
        "POST",
        f"{base_url}/key/update",
        master_key=master_key,
        json_body={"key": virtual_key, "models": remaining},
    )
    for alias, model_ids in targets.items():
        for model_id in model_ids:
            _request(
                "POST",
                f"{base_url}/model/delete",
                master_key=master_key,
                json_body={"id": model_id},
            )
        if not model_ids:
            print(f"Warning: {alias} had no runtime deployment; nothing deleted in the Gateway")
        else:
            print(f"Retired {alias} ({len(model_ids)} deployment(s) removed)")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print without performing")
    subcommands = parser.add_subparsers(dest="command", required=True)

    publish = subcommands.add_parser("publish", help="Publish a new versioned alias")
    publish.add_argument("--alias", required=True, help="e.g. ancoramind-default-r2")
    publish.add_argument("--model", required=True, help="e.g. openrouter/gpt-6-luna")
    publish.add_argument("--rpm", type=int, default=DEFAULT_RPM)
    publish.add_argument("--tpm", type=int, default=DEFAULT_TPM)
    publish.add_argument("--force", action="store_true", help="Publish even if it already exists")
    publish.add_argument("--allow-base", action="store_true", help="Permit a -r1 base alias")

    grant = subcommands.add_parser(
        "grant", help="Add aliases to the AncoraMind virtual key (additive)"
    )
    grant.add_argument("--alias", required=True, nargs="+")

    verify = subcommands.add_parser(
        "verify", help="List published aliases and check the expected ones"
    )
    verify.add_argument("--alias", nargs="+", help="Aliases that must be published")
    verify.add_argument(
        "--smoke",
        action="store_true",
        help="Send one real inference per alias through the virtual key (costs tokens)",
    )

    retire = subcommands.add_parser("retire", help="Ungrant and delete an alias")
    retire.add_argument("--alias", required=True, nargs="+")
    retire.add_argument("--allow-base", action="store_true", help="Permit a -r1 base alias")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    dry_run = bool(args.dry_run)
    try:
        if args.command == "publish":
            return command_publish(args, os.environ, dry_run=dry_run)
        if args.command == "grant":
            return command_grant(args, os.environ, dry_run=dry_run)
        if args.command == "verify":
            return command_verify(args, os.environ, dry_run=dry_run)
        return command_retire(args, os.environ, dry_run=dry_run)
    except AliasError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
