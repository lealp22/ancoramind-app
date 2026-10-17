"""Remote image identity and lifecycle do not grant execution approval."""

import json
from pathlib import Path

import pytest

from scripts import eval_service, eval_source
from scripts.execute_eval_campaign import validate_state_directory

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def packaged(tmp_path):
    for folder in ("src", "scripts", "prompts", "evals"):
        (tmp_path / folder).mkdir()
    (tmp_path / "src" / "example.py").write_text("# synthetic\n", encoding="utf-8")
    (tmp_path / "evals" / "cases.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_image_matches_external_fingerprint_without_git(packaged):
    fingerprint = eval_source.source_fingerprint(packaged)
    eval_source.seal_image(packaged, "a" * 40, fingerprint)
    assert eval_source.source_identity(packaged) == {
        "code_sha": "a" * 40, "source_fingerprint": fingerprint,
        "worktree": "clean", "identity_source": "sealed_image",
    }
    with pytest.raises(FileExistsError):
        eval_source.seal_image(packaged, "a" * 40, fingerprint)


@pytest.mark.parametrize("name", ["src/example.py", "evals/cases.json", "pyproject.toml"])
def test_mutation_after_sealing_fails_closed(packaged, name):
    eval_source.seal_image(packaged, "a" * 40, eval_source.source_fingerprint(packaged))
    (packaged / name).write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance_mismatch"):
        eval_source.source_identity(packaged)


@pytest.mark.parametrize("sha,fingerprint", [("", "b" * 64), ("a" * 40, ""),
                                            ("a" * 40, "b" * 64)])
def test_image_cannot_self_assign_unverified_build_identity(packaged, sha, fingerprint):
    with pytest.raises(ValueError, match="build_identity_required"):
        eval_source.seal_image(packaged, sha, fingerprint)
    assert not (packaged / eval_source.MANIFEST).exists()


def test_missing_or_invalid_manifest_is_not_git_bypass(packaged):
    with pytest.raises(FileNotFoundError):
        eval_source.source_identity(packaged)
    (packaged / eval_source.MANIFEST).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance_mismatch"):
        eval_source.source_identity(packaged)


def test_state_requires_absolute_real_mount_when_remote(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="persistent_state"):
        validate_state_directory(Path("relative"), {})
    with pytest.raises(ValueError, match="persistent_state"):
        validate_state_directory(tmp_path, {"ANCORA_EVAL_REQUIRE_VOLUME": "1"})
    with pytest.raises(ValueError, match="persistent_state"):
        validate_state_directory(tmp_path, {}, sealed_image=True)
    with pytest.raises(ValueError, match="persistent_state"):
        validate_state_directory(Path(tmp_path.anchor), {}, sealed_image=True)
    monkeypatch.setattr(Path, "is_mount", lambda self: self == tmp_path)
    validate_state_directory(tmp_path, {"ANCORA_EVAL_REQUIRE_VOLUME": "1"})


def test_service_start_is_idle_and_signal_stops_without_agent(packaged, monkeypatch, capsys):
    eval_source.seal_image(packaged, "a" * 40, eval_source.source_fingerprint(packaged))
    monkeypatch.setattr(eval_service, "ROOT", packaged)
    handlers = {}
    monkeypatch.setattr(eval_service.signal, "signal",
                        lambda sig, handler: handlers.update({sig: handler}))
    monkeypatch.setattr(eval_service.threading.Event, "wait",
                        lambda self: handlers[eval_service.signal.SIGTERM](15, None))
    assert eval_service.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "idle_manual_only" and report["inference_started"] is False


def test_image_and_config_do_not_inherit_bot_startup_or_public_network():
    recipe = (ROOT / "evals" / "Dockerfile").read_text()
    assert 'CMD ["python", "/app/scripts/eval_service.py"]' in recipe
    assert "EXPOSE" not in recipe and "src.main" not in recipe and "--execute" not in recipe
    assert "ANCORA_EVAL_REQUIRE_VOLUME=1" in recipe
    config = json.loads((ROOT / "evals" / "railway.json").read_text())
    assert config["build"]["dockerfilePath"] == "evals/Dockerfile"
    assert config["deploy"]["restartPolicyType"] == "NEVER"
    assert config["deploy"]["numReplicas"] == 1
    assert "healthcheckPath" not in config["deploy"]
    ignore = (ROOT / "evals" / "Dockerfile.dockerignore").read_text()
    assert "**\n" in ignore and "!.git" not in ignore and "!.env" not in ignore
