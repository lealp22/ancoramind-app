"""Durable review uses synthetic encrypted artifacts, not provider/production I/O."""

import asyncio
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.agent.eval_campaign import EvalCampaignPlan
from src.agent.eval_campaign_runner import TerminalCampaignReviewer, console_data
from src.agent.eval_durable_review import DurableCampaignReviewer, case_record, review_saved
from src.agent.eval_evidence import EvalEvidenceStore
from src.agent.evals import EvalObservation
from src.domain.interactions.reply import AgentReply
from src.domain.runtime_config.models import RuntimeConfigSnapshot

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def archive(tmp_path):
    key = Fernet.generate_key().decode()
    store = EvalEvidenceStore(tmp_path / "evidence", key)
    store.test_key = key
    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text()
    )
    case = plan.validate_snapshot(snapshot)[0]
    identity = {"code_sha": "a" * 40, "source_fingerprint": "b" * 64, "worktree": "clean"}
    run = store.create(identity, plan.model_dump(mode="json"), [case_record(case)],
                       snapshot.model_dump(mode="json", by_alias=True), synthetic_approved=True)
    observation = EvalObservation(
        outcome="tool_call", tool_names=("propose_todo_item",), requires_user_confirmation=True,
        reply=AgentReply(answer="", proposal_text="Propuesta sintética privada creada."),
        proposals=({"kind": "todo_item", "payload": {"title": "póliza privada"}},),
        delivered_text="📋 Propuesta póliza privada",
    )
    reviewer = DurableCampaignReviewer(store, run)
    return store, run, case, observation, reviewer


class Console(io.StringIO):
    def isatty(self):
        return True


def test_evidence_ciphertext_private_metadata_and_duplicate_capture(archive):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    for path in (store.root / run).glob("*.enc"):
        assert b"privada" not in path.read_bytes()
    assert "privada" not in json.dumps(store.status(run))
    with pytest.raises(ValueError, match="already_captured"):
        reviewer.capture(case, observed, {"passed": True})
    recovered = store.observation(run, case.case_id)
    assert recovered["reply"] == observed.reply.model_dump()
    with pytest.raises(ValueError, match="wrong_key"):
        EvalEvidenceStore(store.root, Fernet.generate_key().decode()).events(run)


def test_status_exposes_historical_failure_without_reconstructing_missing_output(archive):
    store, run, case, _, _ = archive
    store.append(run, "checkpoint", {
        "status": "stopped", "inference_started": True, "recorded_model_calls": 5,
        "results": [{"case_id": case.case_id, "status": "stopped",
                     "semantic_status": "not_evaluated",
                     "error_class": "InvalidPresentationOutputError",
                     "private": "PRIVATE_OUTPUT_MUST_NOT_BE_EXPORTED"}],
    })
    summary = store.status(run)
    assert summary["cases"][0]["execution_status"] == "stopped"
    assert summary["cases"][0]["error_class"] == "InvalidPresentationOutputError"
    assert summary["cases"][0]["terminal_diagnostic"] is None
    assert summary["cases"][0]["evidence_available"] is False
    assert "PRIVATE_OUTPUT" not in json.dumps(summary)
    with pytest.raises(ValueError, match="complete_human_review"):
        store.promote(run, case.case_id, dataset="judge", reviewer="owner",
                      sanitized_approved=True, split="development")


def test_status_includes_only_validated_terminal_metadata(archive):
    store, run, case, _, _ = archive
    diagnostic = {"reason": "missing_terminal", "presentation_count": 0,
                  "tool_execution_count": 1, "run_status": "COMPLETED"}
    result = {"case_id": case.case_id, "status": "stopped",
              "error_class": "InvalidPresentationOutputError", "model_calls": 2,
              "usage_error_count": 0, "terminal_diagnostic": diagnostic}
    store.append(run, "checkpoint", {"status": "stopped", "results": [result]})
    summary = store.status(run)["cases"][0]
    assert summary["terminal_diagnostic"] == diagnostic
    assert summary["model_calls"] == 2 and summary["usage_error_count"] == 0
    store.append(run, "checkpoint", {"status": "stopped", "results": [{
        **result, "error_class": "PRIVATE_ERROR_CLASS", "model_calls": "PRIVATE_COUNT",
        "deterministic_status": {"private": "PRIVATE_STATE"},
        "terminal_diagnostic": {**diagnostic, "extra": "PRIVATE_OUTPUT"},
    }]})
    summary = store.status(run)
    assert summary["cases"][0]["terminal_diagnostic"] is None
    assert summary["cases"][0]["model_calls"] is None
    assert summary["cases"][0]["error_class"] == "OtherError"
    assert "PRIVATE" not in json.dumps(summary)


async def test_each_label_is_saved_before_disconnect_and_review_reopens_without_inference(archive):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    class Interrupted(Console):
        reads = 0
        def readline(self, *_):
            self.reads += 1
            if self.reads > 1:
                raise OSError("console disconnected")
            return "p\n"
    with pytest.raises(OSError):
        await review_saved(store, run, "owner", Interrupted(), Console())
    assert set(store.labels(run, case.case_id)) == {0}
    store = EvalEvidenceStore(store.root, store.test_key)  # reopen independent process-equivalent
    writer = Console()
    await review_saved(store, run, "owner", Console("p\n"), writer)
    assert all(item["label"] == "pass" for item in store.labels(run, case.case_id).values())
    assert "Criterio 1" in writer.getvalue() and "Criterio 0" not in writer.getvalue()
    assert "póliza" in writer.getvalue() and "\\u00f3" not in writer.getvalue()


async def test_reviewer_waits_for_persisted_labels_not_live_console(archive):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    task = asyncio.create_task(reviewer.review(case, observed))
    await asyncio.sleep(0)
    assert not task.done()
    store.review(run, case.case_id, 0, "pass", "owner")
    store.review(run, case.case_id, 1, "pass", "owner")
    assert await asyncio.wait_for(task, 3) == ("pass", "pass")


async def test_eof_disconnect_does_not_invent_not_evaluated_and_can_reopen(archive):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    with pytest.raises(EOFError):
        await review_saved(store, run, "owner", Console("p\n"), Console())
    assert list(store.labels(run, case.case_id)) == [0]
    await review_saved(store, run, "owner", Console("p\n"), Console())
    assert all(row["label"] == "pass" for row in store.labels(run, case.case_id).values())


async def test_correction_history_never_reauthorizes_next_inference(archive):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    store.review(run, case.case_id, 0, "fail", "owner", "wrong")
    store.review(run, case.case_id, 0, "pass", "owner", "corrected")
    events = [e for e in store.events(run) if e["kind"] == "review"]
    assert events[1]["data"]["replaces"] == events[0]["sequence"]
    assert store.labels(run, case.case_id)[0]["label"] == "pass"
    assert (await reviewer.review(case, observed))[0] == "fail"


def test_golden_manual_complete_labels_and_separate_datasets(archive, tmp_path):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    with pytest.raises(ValueError, match="complete_human_review"):
        store.promote(run, case.case_id, dataset="judge", reviewer="owner",
                      sanitized_approved=True, split="development")
    store.review(run, case.case_id, 0, "pass", "owner")
    store.review(run, case.case_id, 1, "not_evaluated", "owner")
    with pytest.raises(ValueError, match="complete_human_review"):
        store.promote(run, case.case_id, dataset="judge", reviewer="owner",
                      sanitized_approved=True, split="development")
    store.review(run, case.case_id, 1, "fail", "owner")
    versions = {}
    for dataset in ("agent", "judge"):
        versions[dataset] = store.promote(run, case.case_id, dataset=dataset, reviewer="owner",
                                         sanitized_approved=True, split="development")
        output = tmp_path / (dataset + ".json")
        store.export(versions[dataset], output, sanitized_approved=True)
    agent = json.loads((tmp_path / "agent.json").read_text(encoding="utf-8"))
    judge = json.loads((tmp_path / "judge.json").read_text(encoding="utf-8"))
    assert "reply" not in agent["content"] and "reply" in judge["content"]
    assert judge["content"]["labels"] == ["pass", "fail"]
    assert judge["label_source"] == "human_reviewed"
    assert judge["identity"]["code_sha"] == "a" * 40
    from scripts.run_evals import validate_catalog
    from src.agent.eval_semantic_scoring import load_calibration_labels
    assert validate_catalog(agent["fixture"], tmp_path / case.category / "cases.json"
                            ).case_count == 1
    calibration = load_calibration_labels(judge["fixture"], response_style_cases={
        case.case_id: case.response_criteria,
    })
    assert calibration.label_source == "human_reviewed"
    # Same example cannot leak into validation after being curated for development.
    with pytest.raises(ValueError, match="overlap"):
        store.promote(run, case.case_id, dataset="judge", reviewer="owner",
                      sanitized_approved=True, split="validation")


def test_corruption_deletion_and_symlink_are_not_silently_accepted(archive, tmp_path):
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    store.review(run, case.case_id, 0, "pass", "owner")
    path = store.root / run / "event-000000.enc"
    original = path.read_bytes()
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="wrong_key|chain"):
        store.events(run)
    path.write_bytes(original)
    path.unlink()
    with pytest.raises(ValueError, match="sequence"):
        store.events(run)


def test_secret_markers_are_rejected_not_written_to_artifact(archive):
    store, run, *_ = archive
    for value in ("Bearer abcdefghijklmnop", "sk-this-is-a-synthetic-secret", store.test_key):
        with pytest.raises(ValueError):
            store.append(run, "observation", {"case_id": "synthetic", "content": value})


def test_same_candidate_and_plan_cannot_be_recreated_or_purged_early(archive):
    store, run, *_ = archive
    manifest = store.manifest(run)
    with pytest.raises(FileExistsError):
        store.create(manifest["identity"], manifest["plan"], manifest["cases"],
                     manifest["snapshot"], synthetic_approved=True)
    with pytest.raises(ValueError, match="not_expired"):
        store.purge(run)


def test_retention_purges_content_not_reservation(archive, monkeypatch):
    import src.agent.eval_evidence as evidence
    store, run, *_ = archive
    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(days=8)
    monkeypatch.setattr(evidence, "datetime", Future)
    with pytest.raises(ValueError, match="retention_expired"):
        store.events(run)
    store.purge(run)
    assert not list((store.root / run).glob("*.enc"))
    assert (store.root / run / "purged").exists()
    assert list(store.root.glob("*.reserved"))


async def test_terminal_saves_before_reading_next_criterion_and_escapes_controls(archive):
    _, _, case, observed, _ = archive
    saved = []
    terminal = TerminalCampaignReviewer(Console("p\nf\n"), Console(),
                                        save=lambda i, label: saved.append((i, label)))
    assert await terminal.review(case, observed) == ("pass", "fail")
    assert saved == [(0, "pass"), (1, "fail")]
    assert console_data("Añade póliza\x1b\u202e") == '"Añade póliza\\u001b\\u202e"'


def test_symlink_paths_and_export_overwrite_are_rejected(archive, tmp_path):
    store, run, *_ = archive
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("OS does not grant local symlink privilege")
    with pytest.raises(ValueError, match="directory"):
        EvalEvidenceStore(link, Fernet.generate_key().decode())
    manifest = store.root / run / "manifest.enc"
    raw = manifest.read_bytes()
    manifest.unlink()
    target_file = target / "manifest.enc"
    target_file.write_bytes(raw)
    manifest.symlink_to(target_file)
    with pytest.raises(ValueError, match="path"):
        store.manifest(run)


def test_concurrent_criterion_updates_serialize_history(archive):
    from concurrent.futures import ThreadPoolExecutor
    store, run, case, observed, reviewer = archive
    reviewer.capture(case, observed, {"passed": True})
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(store.review, run, case.case_id, 0, label, "owner")
                   for label in ("pass", "fail")]
        for result in futures:
            result.result()
    events = [e for e in store.events(run) if e["kind"] == "review"]
    assert len(events) == 2
    assert events[1]["data"]["replaces"] == events[0]["sequence"]
    assert not list((store.root / run).glob(".pending-*"))


def test_refuses_capture_of_unapproved_synthetic_content(tmp_path):
    store = EvalEvidenceStore(tmp_path / "data", Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="approval"):
        store.create({"worktree": "clean"}, {}, [{}], {}, synthetic_approved=False)
