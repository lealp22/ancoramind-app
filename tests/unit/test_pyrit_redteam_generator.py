"""Offline tests for the PyRIT phase-A generator (no PyRIT, no network, no LLM)."""

from __future__ import annotations

import asyncio
import json

import pytest

from scripts.pyrit_redteam.generate_deterministic import (
    HOSTILE_CONTEXT_KEYS,
    SEED_CATALOG,
    contains_filtered_phrase,
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

    # Upper-casing keeps the filtered phrase detectable (the check is case-insensitive),
    # so the seeds carrying it produce no variants at all.
    producing = [s for s in seeds if not contains_filtered_phrase(s["context"])]
    assert len(variants) == len(producing) * 2
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


async def _identity(text: str) -> str:
    return text


def test_variants_inherit_the_response_criteria_the_judge_needs() -> None:
    seeds = select_seeds(_cases())
    variants = asyncio.run(generate_variants(seeds, {"tag": _tag}))

    assert variants
    for variant in variants:
        assert variant["expected"]["response_criteria"], variant["id"]


def test_variants_that_keep_the_provider_filtered_phrase_are_dropped() -> None:
    seeds = select_seeds(_cases())
    carriers = [s for s in seeds if contains_filtered_phrase(s["context"])]
    assert carriers, "the catalog must still contain the filtered phrase seeds"

    # An identity converter leaves the phrase intact: those variants cannot be evaluated.
    kept = asyncio.run(generate_variants(seeds, {"same": _identity}))

    kept_seed_ids = {"security." + v["id"].split(".", 1)[1].rsplit("__", 1)[0] for v in kept}
    assert not kept_seed_ids & {s["id"] for s in carriers}
    assert len(kept) == len(seeds) - len(carriers)
    assert not any(contains_filtered_phrase(v["context"]) for v in kept)


def test_a_seed_without_criteria_is_rejected_instead_of_producing_unevaluable_cases() -> None:
    seed = select_seeds(_cases())[0]
    broken = {**seed, "expected": {k: v for k, v in seed["expected"].items()
                                   if k != "response_criteria"}}

    with pytest.raises(ValueError, match="response_criteria"):
        asyncio.run(generate_variants([broken], {"tag": _tag}))


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
