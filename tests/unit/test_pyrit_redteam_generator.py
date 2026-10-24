"""Offline tests for the PyRIT phase-A generator (no PyRIT, no network, no LLM)."""

from __future__ import annotations

import asyncio
import json

from scripts.pyrit_redteam.generate_deterministic import (
    HOSTILE_CONTEXT_KEYS,
    SEED_CATALOG,
    generate_variants,
    select_seeds,
)
from scripts.run_evals import CATEGORIES, EVALS_DIR, validate_catalog


async def _upper(text: str) -> str:
    return text.upper()


async def _tag(text: str) -> str:
    return f"<<{text}>>"


def _cases() -> list[dict]:
    return json.loads(SEED_CATALOG.read_text(encoding="utf-8"))["cases"]


def test_seeds_are_original_attacks_with_hostile_text_only() -> None:
    seeds = select_seeds(_cases())

    assert 1 <= len(seeds) <= 15
    for seed in seeds:
        tags = set(seed["tags"])
        assert "prompt_injection" in tags
        assert not tags & {"benign_control", "false_positive", "injection_variant"}
        assert any(key in HOSTILE_CONTEXT_KEYS for key in seed["context"])


def test_variants_transform_only_hostile_context_and_inherit_expectations() -> None:
    seeds = select_seeds(_cases())
    variants = asyncio.run(generate_variants(seeds, {"upper": _upper, "tag": _tag}))

    assert len(variants) == len(seeds) * 2
    by_id = {seed["id"]: seed for seed in seeds}
    for variant in variants:
        seed_id = "security." + variant["id"].split(".", 1)[1].rsplit("__", 1)[0]
        seed = by_id[seed_id]
        assert variant["input"] == seed["input"], "user input must stay untouched"
        assert variant["expected"] == seed["expected"]
        assert {"pyrit_generated", "candidate"} <= set(variant["tags"])
        for key, value in seed["context"].items():
            assert variant["context"][key] != value or key not in HOSTILE_CONTEXT_KEYS
    assert len({variant["id"] for variant in variants}) == len(variants)


def test_generation_does_not_mutate_the_seed_catalog() -> None:
    seeds = select_seeds(_cases())
    before = json.dumps(seeds, sort_keys=True)

    asyncio.run(generate_variants(seeds, {"upper": _upper}))

    assert json.dumps(seeds, sort_keys=True) == before


def test_candidate_catalog_is_valid_v1_but_outside_the_live_categories(tmp_path) -> None:
    seeds = select_seeds(_cases())
    variants = asyncio.run(generate_variants(seeds, {"upper": _upper}))
    # build_catalog stamps the installed pyrit version, so validate the structural
    # contract on a catalog that does not need PyRIT.
    catalog = {
        "schema_version": 1,
        "category": "security",
        "cases": [{**v, "id": v["id"].replace("security_pyrit.", "security.")} for v in variants],
    }
    path = tmp_path / "security" / "cases.json"
    path.parent.mkdir()
    path.write_text(json.dumps(catalog), encoding="utf-8")

    assert validate_catalog(catalog, path).case_count == len(variants)
    assert "security_pyrit" not in CATEGORIES, "candidates must never join live categories"
    assert not (EVALS_DIR / "security_pyrit" / "cases.json").exists()
