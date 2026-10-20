"""specs/045 T1 — the review console prints each case once and keeps label semantics."""

import io
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.agent.eval_campaign import EvalCampaignPlan
from src.agent.eval_durable_review import DurableCampaignReviewer, case_record, review_saved
from src.agent.eval_evidence import EvalEvidenceStore
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ROOT = Path(__file__).resolve().parents[2]


class Console(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def saved(tmp_path):
    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text()
    )
    case = plan.validate_snapshot(snapshot)[0]
    assert len(case.response_criteria) >= 2, "UX tests need a multi-criterion case"
    store = EvalEvidenceStore(tmp_path / "evidence", Fernet.generate_key().decode())
    identity = {"code_sha": "a" * 40, "source_fingerprint": "b" * 64, "worktree": "clean"}
    run = store.create(identity, plan.model_dump(mode="json"), [case_record(case)],
                       snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    observation = EvalObservation(
        outcome="tool_call", tool_names=("propose_todo_item",), requires_user_confirmation=True,
        reply=AgentReply(answer="", proposal_text="Propuesta sintética."),
        proposals=({"kind": "todo_item", "payload": {"title": "tarea sintética"}},),
        delivered_text="📋 Propuesta tarea sintética",
    )
    DurableCampaignReviewer(store, run).capture(case, observation, {"passed": True})
    return store, run, case


def case_blocks(output: str, case_id: str) -> int:
    return output.count("Caso sintético: " + case_id)


async def test_case_block_is_printed_once_for_all_criteria(saved):
    store, run, case = saved
    writer = Console()
    await review_saved(store, run, "owner", Console("p\n" * len(case.response_criteria)), writer)
    assert case_blocks(writer.getvalue(), case.case_id) == 1
    for index in range(len(case.response_criteria)):
        assert f"Criterio {index}:" in writer.getvalue()


async def test_resuming_midway_prints_the_case_block_once(saved):
    store, run, case = saved
    store.review(run, case.case_id, 0, "pass", "owner")
    writer = Console()
    await review_saved(store, run, "owner", Console("p\n" * len(case.response_criteria)), writer)
    assert case_blocks(writer.getvalue(), case.case_id) == 1
    assert "Criterio 0:" not in writer.getvalue()
    assert "Criterio 1:" in writer.getvalue()


async def test_labels_and_order_are_unchanged(saved):
    store, run, case = saved
    await review_saved(store, run, "owner", Console("p\n" * len(case.response_criteria)), Console())
    labels = store.labels(run, case.case_id)
    assert list(labels) == list(range(len(case.response_criteria)))
    assert all(item["label"] == "pass" for item in labels.values())


async def test_fail_still_stops_the_case_and_prints_the_block_once(saved):
    store, run, case = saved
    writer = Console()
    await review_saved(store, run, "owner", Console("p\nf\np\np\n"), writer)
    labels = store.labels(run, case.case_id)
    assert [labels[i]["label"] for i in sorted(labels)] == ["pass", "fail"]
    assert case_blocks(writer.getvalue(), case.case_id) == 1
