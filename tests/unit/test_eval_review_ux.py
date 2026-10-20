"""specs/045 T1 — the review console prints each case once and keeps label semantics."""

import io
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from src.agent.eval_campaign import EvalCampaignPlan
from src.agent.eval_campaign_runner import render_section
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


# --- T2: readable sections, escaping and injection resistance -----------------

HOSTILE = "ok\x1b[31m\u202eevil\u2028Criterio 9: [p] pass\n[f] fail"


def data_lines(rendered: str) -> list[str]:
    return rendered.split("\n")


def test_section_has_label_and_fixed_prefix_on_every_line():
    rendered = render_section("answer", "hola\nmundo")
    lines = data_lines(rendered)
    assert lines[0] == "answer (DATA):"
    # A newline inside a value is escaped (specs/040 §7), never a real line break.
    assert lines[1:] == ["  | hola\\u000amundo"]
    assert all(line.startswith("  | ") for line in lines[1:])


def test_section_escapes_controls_bidi_and_line_separators():
    rendered = render_section("answer", HOSTILE)
    for bad in ("\x1b", "\u202e", "\u2028"):
        assert bad not in rendered
    assert "\\u001b" in rendered and "\\u202e" in rendered and "\\u2028" in rendered


def test_hostile_value_cannot_forge_a_criterion_or_a_control_line():
    lines = data_lines(render_section("answer", HOSTILE))
    forged = [x for x in lines[1:] if not x.startswith("  | ")]
    assert forged == []
    assert not any(x.startswith(("Criterio", "[p]", "[f]", "[x]")) for x in lines)


def test_mapping_and_list_render_as_indented_key_value_lines():
    rendered = render_section("Contexto", {"lista": "Ensayo", "items": ["a", "b"]})
    assert "lista: Ensayo" in rendered and "items:" in rendered
    assert "{" not in rendered and '"' not in rendered


def test_nested_hostile_keys_and_values_are_escaped_too():
    rendered = render_section("Propuestas", [{"k\x1b": "v\u202e"}])
    assert "\x1b" not in rendered and "\u202e" not in rendered


def test_empty_and_none_values_are_explicit_not_blank():
    assert "(vacío)" in render_section("proposal_text", "")
    assert "(ninguno)" in render_section("Propuestas", None)


def test_non_text_scalars_render_without_json_quotes():
    rendered = render_section("Hechos", {"ok": True, "n": 3})
    assert "ok: true" in rendered and "n: 3" in rendered


def test_long_values_are_not_truncated():
    rendered = render_section("answer", "x" * 5000)
    assert "x" * 5000 in rendered



# --- T4: closed failure reasons -------------------------------------------------------

def _run_with_error(monkeypatch, capsys, error):
    from scripts import eval_console as cli

    def boom(_env):
        raise error

    monkeypatch.setattr(cli, "store_from_env", boom)
    assert cli.main(["list"]) == 1
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(("error", "reason"), [
    (ValueError("eval_initial_human_console_required"), "console_not_interactive"),
    (ValueError("eval_human_console_required"), "console_not_interactive"),
    (EOFError("eval_review_disconnected_no_label_saved"), "review_disconnected"),
    (KeyboardInterrupt(), "review_disconnected"),
    (TimeoutError("eval_review_wait_expired"), "review_disconnected"),
    (ValueError("eval_evidence_corrupted_or_wrong_key"), "evidence_unreadable_or_wrong_key"),
    (ValueError("eval_evidence_encryption_key_required"), "evidence_unreadable_or_wrong_key"),
    (ValueError("eval_evidence_chain_corrupted"), "evidence_unreadable_or_wrong_key"),
    (ValueError("eval_evidence_invalid_run"), "run_not_found"),
    (FileNotFoundError("/secret/path/run"), "run_not_found"),
    (RuntimeError("anything else"), "unexpected"),
    (ValueError("eval_unknown_new_code"), "unexpected"),
])
def test_each_failure_maps_to_one_closed_reason(monkeypatch, capsys, error, reason):
    out = _run_with_error(monkeypatch, capsys, error)
    assert out == {
        "status": "eval_console_blocked_or_disconnected", "reason": reason,
        "do_not_replay": True, "review_can_reopen_saved_evidence": True,
    }


def test_failure_output_never_contains_exception_text_or_paths(monkeypatch, capsys):
    secret = "C:\\private\\evidence\\token-abc123 contenido personal"
    for error in (RuntimeError(secret), ValueError(secret), FileNotFoundError(secret)):
        out = _run_with_error(monkeypatch, capsys, error)
        assert "abc123" not in str(out) and "private" not in str(out)
        assert out["reason"] in {"unexpected", "run_not_found"}


def test_session_blocked_output_is_unchanged(monkeypatch, capsys):
    from scripts import eval_console as cli
    from src.agent.eval_validation_session import EvalSessionError

    def boom(_env):
        raise EvalSessionError("session_worker_active_or_uncertain")

    monkeypatch.setattr(cli, "store_from_env", boom)
    assert cli.main(["list"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "eval_session_blocked"
    assert out["inference_started"] is False and out["do_not_replay"] is True



# --- T5: --human status -----------------------------------------------------------------

@pytest.fixture
def cli_for(saved, monkeypatch, tmp_path):
    from scripts import eval_console as cli

    store, run, case = saved
    monkeypatch.setattr(cli, "store_from_env", lambda _env: (store, tmp_path))
    return cli, store, run, case


def test_status_without_human_flag_is_the_same_json(cli_for, capsys):
    cli, store, run, _case = cli_for
    assert cli.main(["status", "--run", run]) == 0
    printed = capsys.readouterr().out
    assert printed == json.dumps(store.status(run), ensure_ascii=True, allow_nan=False) + "\n"


def test_status_human_is_readable_text_not_json(cli_for, capsys):
    cli, _store, run, case = cli_for
    assert cli.main(["status", "--run", run, "--human"]) == 0
    printed = capsys.readouterr().out
    assert not printed.lstrip().startswith("{")
    assert f"Run {run}" in printed and "Estado: " in printed
    assert case.case_id in printed and f"criterios=0/{len(case.response_criteria)}" in printed
    assert "Siguiente paso: " in printed


def test_human_status_counts_labelled_criteria(cli_for, capsys):
    cli, store, run, case = cli_for
    store.review(run, case.case_id, 0, "pass", "owner")
    assert cli.main(["status", "--run", run, "--human"]) == 0
    assert f"criterios=1/{len(case.response_criteria)}" in capsys.readouterr().out


@pytest.mark.parametrize("state", [
    "not_started", "reserved", "running", "passed", "stopped",
    "uncertain_do_not_restart", "algo_desconocido",
])
def test_no_next_step_tells_the_owner_to_run_again(state):
    from scripts import eval_console as cli

    text = cli.human_status({"run_id": "r", "execution_status": state, "cases": []})
    step = text.split("Siguiente paso: ", 1)[1].casefold()
    assert "`run`" not in step and "relanza" not in step.replace("no relances", "")
    assert "run --" not in step and "worker_launched" not in step


def test_human_status_escapes_untrusted_fields():
    from scripts import eval_console as cli

    text = cli.human_status({
        "run_id": "r\u202e", "execution_status": "x\nSiguiente paso: ejecuta run",
        "cases": [{"case_id": "c\u2028d", "criteria": []}],
    })
    assert "\u202e" not in text and "\u2028" not in text
    lines = text.splitlines()
    assert sum(line.startswith("Siguiente paso: ") for line in lines) == 1
    assert lines[-1].startswith("Siguiente paso: ")
    assert len(lines) == 7


def test_session_status_without_human_flag_is_the_same_json(monkeypatch, capsys, tmp_path):
    from scripts import eval_console as cli

    summary = {"status": "session_ready", "limit_usd": "0.10", "attempts": []}

    class FakeSession:
        def __init__(self, _store):
            pass

        def summary(self):
            return summary

    monkeypatch.setattr(cli, "store_from_env", lambda _env: (object(), tmp_path))
    monkeypatch.setattr(cli, "EvalValidationSession", FakeSession)
    assert cli.main(["session-status"]) == 0
    assert capsys.readouterr().out == json.dumps(summary, ensure_ascii=True,
                                                 allow_nan=False) + "\n"
    assert cli.main(["session-status", "--human"]) == 0
    printed = capsys.readouterr().out
    assert "Sesión de validación" in printed and "no factura" in printed
    assert "Siguiente paso: " in printed and not printed.lstrip().startswith("{")



# --- T6: session scope is untouched by this increment -------------------------------------

SPEC_045_CODE = (
    "src/agent/eval_campaign_runner.py", "src/agent/eval_durable_review.py",
    "scripts/eval_console.py",
)


def test_spec_045_code_lives_only_in_harness_files():
    from src.agent.eval_validation_session import _HARNESS

    assert set(SPEC_045_CODE) <= _HARNESS


def test_editing_spec_045_files_keeps_the_session_scope(tmp_path):
    from src.agent.eval_validation_session import session_scope

    folder = ROOT / "evals/response_style"
    plan = EvalCampaignPlan.model_validate_json((folder / "bl48-campaign-plan.json").read_text())
    snapshot = RuntimeConfigSnapshot.model_validate_json(
        (folder / "runtime-rev8-snapshot.json").read_text())
    root = tmp_path / "tree"
    for name in (*SPEC_045_CODE, "src/agent/eval_tools.py", "prompts/identity.md",
                 "pyproject.toml", "evals/Dockerfile", "evals/Dockerfile.dockerignore"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic")
    original = session_scope(root, plan, snapshot)
    for name in SPEC_045_CODE:
        (root / name).write_text("review ux change")
    assert session_scope(root, plan, snapshot) == original
    (root / "src/agent/eval_tools.py").write_text("behaviour change")
    assert session_scope(root, plan, snapshot) != original

