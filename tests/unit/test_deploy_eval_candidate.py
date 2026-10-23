"""Manual remote publication contracts. No CLI installed, tokens or live upload."""

import copy
import io
import json
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from scripts import deploy_eval_candidate as deploy
from scripts.eval_source import source_fingerprint

COMMIT = "a" * 40
DEPLOYMENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@pytest.fixture
def observed_status():
    return json.loads((Path(__file__).parent / "fixtures/railway_eval_inventory.json").read_text(
        encoding="utf-8",
    ))["status"]


@pytest.fixture
def observed_empty_pending():
    """Sanitized API shape after committing variables without deploying; no values."""
    fixture = Path(__file__).parent / "fixtures/railway_eval_empty_pending.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def test_observed_no_draft_sentinel_is_verified_not_assumed(observed_empty_pending):
    deploy.validate_pending_work(observed_empty_pending)


def test_observed_cli_projection_null_legacy_replica_is_not_drift(observed_status):
    others, service = deploy.inventory(observed_status)
    assert len(others) == 6
    assert service["numReplicas"] is None
    assert service["latestDeployment"]["instances"][0]["status"] == "RUNNING"


@pytest.mark.parametrize("change", [
    "legacy_multiple", "legacy_false", "legacy_missing", "meta_missing", "meta_null",
    "meta_string", "manifest_missing", "deploy_list", "regions_empty", "regions_multiple",
    "regions_null", "region_null", "count_missing", "count_false", "count_string",
    "count_multiple", "count_zero",
])
def test_replica_null_never_defaults_to_one_without_valid_evidence(observed_status, change):
    environment = observed_status["environments"]["edges"][0]["node"]
    node = environment["serviceInstances"]["edges"][3]["node"]
    latest = node["latestDeployment"]
    config = latest["meta"]["serviceManifest"]["deploy"]
    regions = config["multiRegionConfig"]
    if change == "legacy_multiple":
        node["numReplicas"] = 2
    elif change == "legacy_false":
        node["numReplicas"] = False
    elif change == "legacy_missing":
        del node["numReplicas"]
    elif change == "meta_missing":
        del latest["meta"]
    elif change == "meta_null":
        latest["meta"] = None
    elif change == "meta_string":
        latest["meta"] = "PRIVATE_NOT_METADATA"
    elif change == "manifest_missing":
        latest["meta"] = {}
    elif change == "deploy_list":
        latest["meta"]["serviceManifest"]["deploy"] = []
    elif change == "regions_empty":
        config["multiRegionConfig"] = {}
    elif change == "regions_multiple":
        regions["other-region"] = {"numReplicas": 1}
    elif change == "regions_null":
        config["multiRegionConfig"] = None
    elif change == "region_null":
        regions["europe-west4-drams3a"] = None
    elif change == "count_missing":
        regions["europe-west4-drams3a"] = {}
    else:
        regions["europe-west4-drams3a"]["numReplicas"] = {
            "count_false": False, "count_string": "1", "count_multiple": 2, "count_zero": 0,
        }[change]
    with pytest.raises(ValueError, match="eval_deploy_replica_") as error:
        deploy.inventory(observed_status)
    assert "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("count", [1, 2, None, False, "1"])
def test_manifest_explicit_count_without_region_map_is_never_defaulted(observed_status, count):
    environment = observed_status["environments"]["edges"][0]["node"]
    node = environment["serviceInstances"]["edges"][3]["node"]
    node["latestDeployment"]["meta"]["serviceManifest"]["deploy"] = {"numReplicas": count}
    if type(count) is int and count == 1:
        assert deploy.single_replica_evidence(node) == "deployment_manifest_explicit_count"
    else:
        with pytest.raises(ValueError, match="replica_configuration_drift"):
            deploy.inventory(observed_status)


@pytest.mark.parametrize("check_only", [False, True])
@pytest.mark.parametrize("pending_states", [
    ("draft", "draft"), ("empty", "empty"), ("draft", "empty"), ("empty", "draft"),
])
def test_full_cli_adapter_contract_with_observed_projection(
    monkeypatch, candidate, observed_status, observed_empty_pending, env, check_only,
    pending_states, capsys,
):
    """Real adapter/CLI JSON boundaries, not FakeRailway.status skipping validation."""
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    environment = observed_status["environments"]["edges"][0]["node"]
    node = environment["serviceInstances"]["edges"][3]["node"]
    calls = []
    pending_checks = []
    def run(argv, **kwargs):
        assert kwargs["capture_output"] is True and kwargs["check"] is False
        assert kwargs["env"]["RAILWAY_TOKEN"] == "synthetic"
        args = argv[1:]
        calls.append(args)
        if args == ["--version"]:
            result = "railway " + deploy.CLI_VERSION
        elif args == ["status", *deploy.TARGET, "--json"]:
            result = json.dumps(observed_status)
        elif args[0] == "api":
            assert args[1].startswith("query {")
            state = pending_states[len(pending_checks)]
            pending_checks.append(state)
            result = json.dumps(observed_empty_pending if state == "empty" else {
                "data": pending_state(),
            })
        elif args[0] == "variable":
            assert check_only is False and "--skip-deploys" in args
            result = "updated keys"
        elif args[0] == "up":
            assert check_only is False
            assert "--detach" in args and "--json" in args and "--path-as-root" in args
            assert kwargs["cwd"] == candidate[0] / "context"
            node["latestDeployment"]["id"] = DEPLOYMENT
            result = json.dumps({"deploymentId": DEPLOYMENT, "logsUrl": "https://railway.com"})
        elif args == ["deployment", "list", *deploy.SERVICE_TARGET, "--json", "--limit", "20"]:
            result = json.dumps([{"id": DEPLOYMENT, "status": "SUCCESS", "meta": None}])
        elif args == ["logs", DEPLOYMENT, *deploy.SERVICE_TARGET, "--json", "--lines", "50"]:
            result = json.dumps({"message": json.dumps({
                "status": "idle_manual_only", "inference_started": False, "code_sha": COMMIT,
                "source_fingerprint": candidate[1]["source_fingerprint"],
                "worktree": "clean", "identity_source": "sealed_image",
            })})
        else:
            raise AssertionError("unexpected command")
        return subprocess.CompletedProcess(argv, 0, stdout=result, stderr="")
    monkeypatch.setattr(deploy.subprocess, "run", run)
    report = deploy.publish(
        candidate[0], env, deploy.Railway("synthetic"), {}, check_only=check_only,
    )
    assert report["replica_evidence"] == "deployment_manifest_single_region"
    assert report["preflight_verified"] is True
    if check_only:
        assert report["status"] == "preflight_verified_no_upload"
        assert [args[0] for args in calls] == ["--version", "status", "api"]
        assert len(pending_checks) == 1
    else:
        assert report["status"] == "deployed_idle_verified"
        assert len([args for args in calls if args[0] == "up"]) == 1
        assert len([args for args in calls if args[0] == "variable"]) == 1
        assert len(pending_checks) == 2
    assert "serviceManifest" not in json.dumps(report) + capsys.readouterr().out


@pytest.mark.parametrize("flag", ["true", "false", "invalid"])
def test_main_check_only_flag_is_explicit(monkeypatch, candidate, flag):
    monkeypatch.setenv("EVAL_DEPLOY_CHECK_ONLY", flag)
    railway = Mock()
    publish = Mock(return_value={"status": "synthetic", "inference_started": False})
    monkeypatch.setattr(deploy, "Railway", Mock(return_value=railway))
    monkeypatch.setattr(deploy, "publish", publish)
    expected = 1 if flag == "invalid" else 0
    assert deploy.main(["publish", "--directory", str(candidate[0])]) == expected
    if flag == "invalid":
        publish.assert_not_called()
    else:
        assert publish.call_args.kwargs["check_only"] is (flag == "true")


@pytest.mark.parametrize("change,reason", [
    ("start", "start_command_drift"), ("identity", "service_identity_drift"),
    ("domain", "exposure_schedule_or_tracing_drift"),
    ("tracing_unknown", "exposure_schedule_or_tracing_drift"),
    ("cron_missing", "exposure_schedule_or_tracing_drift"),
    ("volume", "volume_drift"), ("replicas", "replica_configuration_drift"),
])
def test_preflight_reports_specific_safe_drift_before_any_mutation(
    observed_status, candidate, env, change, reason, capsys,
):
    environment = observed_status["environments"]["edges"][0]["node"]
    service = environment["serviceInstances"]["edges"][3]["node"]
    if change == "start":
        service["startCommand"] = "PRIVATE_CONTENT"
    elif change == "identity":
        service["serviceName"] = "PRIVATE_CONTENT"
    elif change == "domain":
        service["domains"]["serviceDomains"] = [{"domain": "PRIVATE_CONTENT"}]
    elif change == "tracing_unknown":
        del service["tracingEnabled"]
    elif change == "cron_missing":
        del service["cronSchedule"]
    elif change == "volume":
        environment["volumeInstances"]["edges"][0]["node"]["mountPath"] = "PRIVATE_CONTENT"
    else:
        service["latestDeployment"]["meta"]["serviceManifest"]["deploy"]["multiRegionConfig"] = {
            "region": {"numReplicas": 2},
        }
    railway = FakeRailway(observed_status, candidate[1])
    with pytest.raises(ValueError, match="eval_deploy_" + reason) as error:
        deploy.publish(candidate[0], env, railway, {}, check_only=True)
    assert railway.calls == [["--version"]]
    assert "PRIVATE_CONTENT" not in str(error.value) + capsys.readouterr().out


@pytest.fixture
def env():
    return {"GITHUB_REPOSITORY": deploy.REPO, "GITHUB_REF": "refs/heads/main",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "EVAL_CONFIRM_IDLE": "true",
            "RUNNER_ENVIRONMENT": "github-hosted", "GH_TOKEN": "synthetic-not-real",
            "CANDIDATE_SHA": COMMIT, "GITHUB_SHA": COMMIT}


@pytest.fixture
def candidate(tmp_path):
    folder = tmp_path / "candidate"
    context = folder / "context"
    files = {"pyproject.toml": "# fixture", "README.md": "synthetic",
             "evals/Dockerfile": "FROM python:3.12-slim\n",
             "evals/Dockerfile.dockerignore": "**\n!src/**\n",
             "src/example.py": "# never execute", "scripts/eval_service.py": "# idle"}
    for name, text in files.items():
        path = context / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (context / "Dockerfile").write_bytes((context / "evals/Dockerfile").read_bytes())
    (context / ".dockerignore").write_bytes(
        (context / "evals/Dockerfile.dockerignore").read_bytes(),
    )
    metadata = {"code_sha": COMMIT, "source_fingerprint": source_fingerprint(context),
                "prepared_archive_sha256": "b" * 64, "ci_run_id": 123, "ci_attempt": 1,
                "publication_code_sha": COMMIT,
                "status": "prepared_no_upload", "inference_started": False}
    (folder / "candidate.json").write_text(json.dumps(metadata), encoding="utf-8")
    return folder, metadata


@pytest.fixture
def status():
    service = {"serviceId": deploy.SERVICE, "serviceName": "ancoramind-evals",
               "startCommand": "python /app/scripts/eval_service.py", "numReplicas": 1,
               "cronSchedule": None, "tracingEnabled": False, "autoInstrumentationEnabled": False,
               "domains": {"serviceDomains": [], "customDomains": []},
               "latestDeployment": {"id": DEPLOYMENT, "status": "SUCCESS",
                                    "instances": [{"status": "RUNNING"}]}}
    return {"id": deploy.PROJECT, "environments": {"edges": [{"node": {
        "id": deploy.ENVIRONMENT, "unmergedChangesCount": 0,
        "serviceInstances": {"edges": [{"node": service}, {"node": {
            "serviceId": "other-service", "latestDeployment": {"id": "unchanged"},
        }}]},
        "volumeInstances": {"edges": [{"node": {
            "volume": {"id": deploy.VOLUME}, "serviceId": deploy.SERVICE,
            "mountPath": "/eval-state", "deletedAt": None, "isPendingDeletion": False,
        }}]},
    }}]}}


class FakeRailway:
    def __init__(self, value, metadata):
        self.value, self.metadata = value, metadata
        self.calls = []
        self.deployment_status = "SUCCESS"
        self.raw_logs = None

    def status(self):
        return copy.deepcopy(self.value)

    def call(self, args, **kwargs):
        self.calls.append(args)
        if args == ["--version"]:
            return "railway " + deploy.CLI_VERSION
        if args[0] == "variable":
            return "updated keys"
        if args[0] == "up":
            return json.dumps({"deploymentId": DEPLOYMENT})
        if args[0] == "deployment":
            return json.dumps([{"id": DEPLOYMENT, "status": self.deployment_status}])
        if args[0] == "logs":
            return self.raw_logs or json.dumps({
                "status": "idle_manual_only", "inference_started": False,
                "code_sha": COMMIT, "source_fingerprint": self.metadata["source_fingerprint"],
                "worktree": "clean", "identity_source": "sealed_image",
            })
        raise AssertionError(args)


@pytest.mark.parametrize("field,value", [
    ("GITHUB_REF", "refs/heads/unsafe"), ("GITHUB_EVENT_NAME", "push"),
    ("GITHUB_REPOSITORY", "other/repo"), ("EVAL_CONFIRM_IDLE", "false"),
    ("RUNNER_ENVIRONMENT", "self-hosted"),
])
def test_dispatch_requires_main_manual_idle_and_hosted_runner(env, field, value):
    env[field] = value
    with pytest.raises(ValueError, match="manual_main"):
        deploy.validate_dispatch(COMMIT, env)


@pytest.mark.parametrize("sha", ["main", "a" * 7, "a" * 39 + ";", "A" * 40, "$(secret)"])
def test_no_sha_injection_or_implicit_branch(env, sha):
    with pytest.raises(ValueError):
        deploy.validate_dispatch(sha, env)


def test_ci_gate_latest_same_sha_push_main_attempt_and_job_names(monkeypatch):
    runs = [{"id": 123, "run_number": 5, "run_attempt": 2, "head_sha": COMMIT,
             "head_branch": "main", "event": "push", "status": "completed",
             "conclusion": "success"}]
    requests = []
    def github(path, token):
        requests.append(path)
        if "ci.yml/runs" in path:
            return {"workflow_runs": runs}
        return {"jobs": [{"name": name, "conclusion": "success", "status": "completed"}
                         for name in (
            "quality", "integration", "collector-config",
        )]}
    monkeypatch.setattr(deploy, "github_get", github)
    assert deploy.ci_gate(COMMIT, "synthetic")["ci_attempt"] == 2
    assert "/attempts/2/jobs" in requests[-1]
    runs.append({**runs[0], "run_number": 6, "id": 124, "conclusion": "failure"})
    with pytest.raises(ValueError, match="latest_ci"):
        deploy.ci_gate(COMMIT, "synthetic")
    runs[1]["conclusion"] = "success"
    runs[1]["status"] = "in_progress"
    with pytest.raises(ValueError, match="latest_ci"):
        deploy.ci_gate(COMMIT, "synthetic")


@pytest.mark.parametrize("jobs", [[], [{"name": "quality", "conclusion": "skipped"}],
                                   [{"name": "quality", "conclusion": "success"}]])
def test_missing_skipped_jobs_cannot_unlock_publication(monkeypatch, jobs):
    run = {"id": 123, "run_number": 1, "run_attempt": 1, "head_sha": COMMIT,
           "head_branch": "main", "event": "push", "status": "completed",
           "conclusion": "success"}
    monkeypatch.setattr(deploy, "github_get", lambda path, _: {
        "workflow_runs": [run],
    } if "ci.yml/runs" in path else {"jobs": jobs})
    with pytest.raises(ValueError, match="required_job"):
        deploy.ci_gate(COMMIT, "synthetic")


def test_package_no_candidate_execution_or_secrets(candidate, env, monkeypatch, tmp_path):
    folder, _ = candidate
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for path in (folder / "context").rglob("*"):
            if path.is_file():
                archive.add(path, arcname=path.relative_to(folder / "context").as_posix())
        for name in (".env", "railway.json", "data/private.db"):
            info = tarfile.TarInfo(name)
            info.size = 6
            archive.addfile(info, io.BytesIO(b"secret"))
    calls = []
    def git(root, *args):
        calls.append(args)
        return raw.getvalue() if args[0] == "archive" else b""
    monkeypatch.setattr(deploy, "git", git)
    monkeypatch.setattr(deploy, "ci_gate", lambda *_: {"ci_run_id": 123, "ci_attempt": 1})
    destination = tmp_path / "new-package"
    metadata = deploy.prepare(tmp_path, COMMIT, destination, env)
    assert calls == [("merge-base", "--is-ancestor", COMMIT, "origin/main"),
                     ("archive", "--format=tar", COMMIT)]
    assert not (destination / "context/railway.json").exists()
    assert not (destination / "context/.env").exists()
    assert not (destination / "context/data").exists()
    assert metadata["inference_started"] is False
    assert source_fingerprint(destination / "context") == metadata["source_fingerprint"]


@pytest.mark.parametrize("unmerged_count", [0, None])
def test_publish_only_three_metadata_variables_and_fixed_existing_service(
    candidate, status, env, capsys, unmerged_count,
):
    status["environments"]["edges"][0]["node"]["unmergedChangesCount"] = unmerged_count
    directory, metadata = candidate
    railway = FakeRailway(status, metadata)
    report = deploy.publish(directory, env, railway, {})
    assert report["status"] == "deployed_idle_verified"
    assert report["volume_preserved"] and report["other_services_unchanged"]
    assert report["inference_started"] is False
    for args in railway.calls[1:]:
        assert args[args.index("--service") + 1] == deploy.SERVICE
        assert args[args.index("--environment") + 1] == deploy.ENVIRONMENT
        assert args[args.index("--project") + 1] == deploy.PROJECT
    mutation = next(args for args in railway.calls if args[:2] == ["variable", "set"])
    assert "--skip-deploys" in mutation
    assert {a.split("=", 1)[0] for a in mutation if "=" in a} == {
        "ANCORA_EVAL_BUILD_SHA", "ANCORA_EVAL_BUILD_SOURCE", "RAILWAY_DOCKERFILE_PATH",
    }
    assert sum(args[0] == "up" for args in railway.calls) == 1
    assert "--path-as-root" in next(args for args in railway.calls if args[0] == "up")
    assert "PRIVATE" not in capsys.readouterr().out


@pytest.mark.parametrize("count", [1, -1, "0", False, [], {}])
def test_unmerged_count_invalid_blocks_before_mutation(candidate, status, env, count):
    status["environments"]["edges"][0]["node"]["unmergedChangesCount"] = count
    railway = FakeRailway(status, candidate[1])
    with pytest.raises(ValueError, match="pending_changes_or_wrong_environment"):
        deploy.publish(candidate[0], env, railway, {})
    assert not any(args[0] in {"up", "variable"} for args in railway.calls)


def test_unmerged_count_missing_blocks_before_mutation(candidate, status, env):
    del status["environments"]["edges"][0]["node"]["unmergedChangesCount"]
    railway = FakeRailway(status, candidate[1])
    with pytest.raises(ValueError, match="pending_changes_or_wrong_environment"):
        deploy.publish(candidate[0], env, railway, {})
    assert not any(args[0] in {"up", "variable"} for args in railway.calls)


@pytest.mark.parametrize("change", ["volume", "pending", "start", "domain", "replicas"])
def test_inventory_drift_blocks_before_mutation(candidate, status, env, change):
    environment = status["environments"]["edges"][0]["node"]
    service = environment["serviceInstances"]["edges"][0]["node"]
    if change == "volume":
        environment["volumeInstances"]["edges"][0]["node"]["mountPath"] = "/wrong"
    elif change == "pending":
        environment["unmergedChangesCount"] = 1
    elif change == "start":
        service["startCommand"] = "python -m src.main"
    elif change == "domain":
        service["domains"]["serviceDomains"] = [{"domain": "public.example"}]
    else:
        service["numReplicas"] = 2
    railway = FakeRailway(status, candidate[1])
    with pytest.raises(ValueError):
        deploy.publish(candidate[0], env, railway, {})
    assert not any(args[0] in {"up", "variable"} for args in railway.calls)


def test_wrong_idle_identity_or_not_running_is_not_success(candidate, status, env, monkeypatch):
    railway = FakeRailway(status, candidate[1])
    railway.raw_logs = '{"status":"idle_manual_only","code_sha":"wrong","content":"PRIVATE"}'
    clock = iter([0, 0, 100])
    monkeypatch.setattr(deploy.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(deploy.time, "sleep", lambda _: None)
    report = {}
    with pytest.raises(TimeoutError):
        deploy.publish(candidate[0], env, railway, report, wait_seconds=1)
    assert report["deployment_id"] == DEPLOYMENT
    assert report["status"] == "uploaded_not_verified"
    assert sum(args[0] == "up" for args in railway.calls) == 1


def test_deployment_failure_is_not_retried(candidate, status, env):
    railway = FakeRailway(status, candidate[1])
    railway.deployment_status = "FAILED"
    with pytest.raises(ValueError, match="failed_no_automatic_retry"):
        deploy.publish(candidate[0], env, railway, {})
    assert sum(args[0] == "up" for args in railway.calls) == 1


def test_context_tamper_blocks_before_remote_commands(candidate, status, env):
    directory, metadata = candidate
    (directory / "context/.env").write_text("PRIVATE")
    railway = FakeRailway(status, metadata)
    with pytest.raises(ValueError, match="unexpected_file"):
        deploy.publish(directory, env, railway, {})
    assert railway.calls == []


def test_idle_log_accepts_cli_flattened_and_json_message_only_exact(candidate):
    fingerprint = candidate[1]["source_fingerprint"]
    record = {"status": "idle_manual_only", "code_sha": COMMIT,
              "source_fingerprint": fingerprint, "worktree": "clean",
              "identity_source": "sealed_image", "inference_started": False}
    assert deploy.idle_log(json.dumps(record), COMMIT, fingerprint)
    assert deploy.idle_log(json.dumps({"message": json.dumps(record)}), COMMIT, fingerprint)
    record["inference_started"] = True
    assert not deploy.idle_log(json.dumps(record), COMMIT, fingerprint)


def test_cli_environment_excludes_github_and_model_keys(monkeypatch):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    monkeypatch.setenv("ANCORA_EVAL_GATEWAY_KEY", "PRIVATE_LLM")
    monkeypatch.setenv("GITHUB_TOKEN", "PRIVATE_GITHUB")
    call = Mock(return_value=subprocess.CompletedProcess([], 1, stdout="PRIVATE", stderr="PRIVATE"))
    monkeypatch.setattr(deploy.subprocess, "run", call)
    railway = deploy.Railway("PRIVATE_DEPLOY")
    with pytest.raises(ValueError, match="command_failed") as error:
        railway.call(["status", *deploy.TARGET, "--json"])
    assert "PRIVATE" not in str(error.value)
    assert "ANCORA_EVAL_GATEWAY_KEY" not in call.call_args.kwargs["env"]
    assert "GITHUB_TOKEN" not in call.call_args.kwargs["env"]


@pytest.mark.parametrize("unmerged_count", [0, None])
def test_empty_staged_draft_allows_publication_without_applying_it(
    monkeypatch, candidate, status, env, unmerged_count, capsys,
):
    status["environments"]["edges"][0]["node"]["unmergedChangesCount"] = unmerged_count
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    railway = deploy.Railway("synthetic")
    fake = FakeRailway(status, candidate[1])
    queries = []
    def call(args, **kwargs):
        if args[0] == "status":
            return json.dumps(status)
        if args[0] == "api":
            queries.append(args[1])
            return json.dumps({"data": pending_state()})
        return fake.call(args, **kwargs)
    monkeypatch.setattr(railway, "call", call)
    report = deploy.publish(candidate[0], env, railway, {})
    assert report["status"] == "deployed_idle_verified"
    assert len(queries) == 2  # The same strict guard runs before and after upload.
    assert all("environmentPendingWork" in query and "patch" in query for query in queries)
    assert all("changes" not in query and "variables" not in query for query in queries)
    assert len([args for args in fake.calls if args[0] == "up"]) == 1
    assert not any("mutation" in query or "Commit" in query for query in queries)
    assert "environmentStagedChanges" not in capsys.readouterr().out


def pending_state():
    return {
        "environmentStagedChanges": {
            "id": DEPLOYMENT, "status": "STAGED", "environmentId": deploy.ENVIRONMENT,
            "patch": {},
        },
        "environmentPendingWork": [{
            "id": "patch:" + DEPLOYMENT, "kind": "EnvironmentPatch", "status": "staged",
            "environmentId": deploy.ENVIRONMENT, "children": [],
        }],
    }


@pytest.mark.parametrize("no_draft", [False, True])
def test_pending_changes_after_upload_never_trigger_another_mutation(
    monkeypatch, candidate, status, observed_empty_pending, env, no_draft,
):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    railway = deploy.Railway("synthetic")
    fake = FakeRailway(status, candidate[1])
    checks = []
    def call(args, **kwargs):
        if args[0] == "status":
            return json.dumps(status)
        if args[0] == "api":
            data = observed_empty_pending["data"] if no_draft else pending_state()
            if checks:
                data["environmentStagedChanges"]["patch"] = {"services": {}}
            checks.append(True)
            return json.dumps({"data": data})
        return fake.call(args, **kwargs)
    monkeypatch.setattr(railway, "call", call)
    report = {}
    with pytest.raises(ValueError, match="pending_changes"):
        deploy.publish(candidate[0], env, railway, report)
    assert report["status"] == "uploaded_not_verified"
    assert len(checks) == 2
    assert len([args for args in fake.calls if args[0] == "up"]) == 1
    assert len([args for args in fake.calls if args[0] == "variable"]) == 1


@pytest.mark.parametrize("patch", [
    None, [], False, 0, "{}", {"services": {}}, {"sharedVariables": {}},
    {"privateNetworkDisabled": False}, {"services": {"other": {"isDeleted": True}}},
    {"sharedVariables": {"PRIVATE_TOKEN": "SYNTHETIC_PRIVATE"}},
])
def test_only_exact_empty_patch_accepted(patch):
    data = pending_state()
    data["environmentStagedChanges"]["patch"] = patch
    with pytest.raises(ValueError, match="eval_deploy_pending_"):
        deploy.validate_pending_work({"data": data})


@pytest.mark.parametrize("change", [
    "missing_patch", "missing_stage", "null_stage", "bad_stage_id", "wrong_stage_env",
    "applying", "failed", "unknown_stage", "missing_pending", "null_pending",
    "empty_pending", "wrong_pending_id", "wrong_pending_env", "wrong_kind",
    "pending_applying", "children", "missing_children", "other_deployment",
    "wrong_data_type", "errors",
])
def test_pending_work_unknown_or_in_progress_blocks_before_mutation(
    monkeypatch, candidate, status, env, change, capsys,
):
    data = pending_state()
    staged, pending = data["environmentStagedChanges"], data["environmentPendingWork"]
    response = {"data": data}
    if change == "missing_patch":
        del staged["patch"]
    elif change == "missing_stage":
        del data["environmentStagedChanges"]
    elif change == "null_stage":
        data["environmentStagedChanges"] = None
    elif change == "bad_stage_id":
        staged["id"] = "SYNTHETIC_PRIVATE"
    elif change == "wrong_stage_env":
        staged["environmentId"] = "other"
    elif change in {"applying", "failed", "unknown_stage"}:
        staged["status"] = change.upper()
    elif change == "missing_pending":
        del data["environmentPendingWork"]
    elif change == "null_pending":
        data["environmentPendingWork"] = None
    elif change == "empty_pending":
        data["environmentPendingWork"] = []
    elif change == "wrong_pending_id":
        pending[0]["id"] = "patch:other"
    elif change == "wrong_pending_env":
        pending[0]["environmentId"] = "other"
    elif change == "wrong_kind":
        pending[0]["kind"] = "Deployment"
    elif change == "pending_applying":
        pending[0]["status"] = "applying"
    elif change == "children":
        pending[0]["children"] = [{"id": "running-deploy"}]
    elif change == "missing_children":
        del pending[0]["children"]
    elif change == "other_deployment":
        pending.append({"id": "other", "kind": "Deployment", "status": "deploying"})
    elif change == "wrong_data_type":
        response["data"] = []
    else:
        response["errors"] = [{"message": "SYNTHETIC_PRIVATE"}]
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    railway = deploy.Railway("synthetic")
    calls = []
    def call(args, **kwargs):
        calls.append(args)
        if args == ["--version"]:
            return "railway " + deploy.CLI_VERSION
        if args[0] == "status":
            return json.dumps(status)
        if args[0] == "api":
            return json.dumps(response)
        raise AssertionError("no mutation allowed")
    monkeypatch.setattr(railway, "call", call)
    with pytest.raises(ValueError, match="eval_deploy_pending_") as error:
        deploy.publish(candidate[0], env, railway, {})
    assert "SYNTHETIC_PRIVATE" not in str(error.value) + capsys.readouterr().out
    assert not any(args[0] in {"up", "variable"} for args in calls)


@pytest.mark.parametrize("change", [
    "id_missing", "id_null", "id_empty", "id_case", "id_whitespace", "id_uuid",
    "status_missing", "status_applying", "status_null", "environment_missing",
    "environment_wrong", "patch_missing", "patch_null", "patch_string", "patch_list",
    "patch_nonempty", "pending_missing", "pending_null", "pending_object",
    "pending_draft", "pending_deployment", "errors",
])
def test_no_draft_sentinel_inconsistency_blocks_before_writes(
    monkeypatch, candidate, status, observed_empty_pending, env, change, capsys,
):
    response = observed_empty_pending
    data = response["data"]
    staged = data["environmentStagedChanges"]
    if change.endswith("_missing"):
        field = change.removesuffix("_missing")
        if field == "pending":
            del data["environmentPendingWork"]
        else:
            del staged["environmentId" if field == "environment" else field]
    elif change == "errors":
        response["errors"] = [{"message": "SYNTHETIC_PRIVATE"}]
    elif change.startswith("pending_"):
        data["environmentPendingWork"] = {
            "pending_null": None, "pending_object": {},
            "pending_draft": pending_state()["environmentPendingWork"],
            "pending_deployment": [{"id": "other", "kind": "Deployment", "status": "deploying"}],
        }[change]
    else:
        field, value = {
            "id_null": ("id", None), "id_empty": ("id", ""),
            "id_case": ("id", "<EMPTY>"), "id_whitespace": ("id", "<empty> "),
            "id_uuid": ("id", DEPLOYMENT), "status_applying": ("status", "APPLYING"),
            "status_null": ("status", None), "environment_wrong": ("environmentId", "other"),
            "patch_null": ("patch", None), "patch_string": ("patch", "{}"),
            "patch_list": ("patch", []),
            "patch_nonempty": ("patch", {"private": "SYNTHETIC_PRIVATE"}),
        }[change]
        staged[field] = value
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    call = Mock(side_effect=["railway " + deploy.CLI_VERSION, json.dumps(status),
                             json.dumps(response)])
    monkeypatch.setattr(deploy.subprocess, "run", Mock(side_effect=AssertionError("no real CLI")))
    railway = deploy.Railway("synthetic")
    monkeypatch.setattr(railway, "call", call)
    with pytest.raises(ValueError, match="eval_deploy_pending_") as error:
        deploy.publish(candidate[0], env, railway, {})
    assert [entry.args[0][0] for entry in call.call_args_list] == ["--version", "status", "api"]
    assert "SYNTHETIC_PRIVATE" not in str(error.value) + capsys.readouterr().out


@pytest.mark.parametrize("no_draft", [False, True])
def test_nonempty_patch_values_never_reach_stdout_or_summary(
    monkeypatch, candidate, status, observed_empty_pending, env, tmp_path, capsys, no_draft,
):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("RAILWAY_TOKEN", "synthetic")
    data = observed_empty_pending["data"] if no_draft else pending_state()
    data["environmentStagedChanges"]["patch"] = {
        "sharedVariables": {"PRIVATE_KEY": "SYNTHETIC_PRIVATE"},
    }
    responses = ["railway " + deploy.CLI_VERSION, json.dumps(status), json.dumps({"data": data})]
    call = Mock(side_effect=responses)
    monkeypatch.setattr(deploy.Railway, "call", call)
    assert deploy.main(["publish", "--directory", str(candidate[0])]) == 1
    output = capsys.readouterr()
    text = output.out + output.err + summary.read_text(encoding="utf-8")
    assert "SYNTHETIC_PRIVATE" not in text and "PRIVATE_KEY" not in text
    assert "eval_deploy_pending_changes" in text
    assert call.call_count == 3


def test_workflow_manual_secret_only_publish_and_remote_install():
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/deploy-evals.yml"
                ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow and "  push:" not in workflow
    assert "pull_request" not in workflow and "schedule:" not in workflow
    assert "cancel-in-progress: false" in workflow
    assert "environment: ancoramind-evals-deploy" in workflow
    assert workflow.count("${{ secrets.") == 1
    assert workflow.index("${{ secrets.") > workflow.index("Check exact CI")
    assert "persist-credentials: false" in workflow
    assert "@railway/cli@5.70.0" in workflow
    assert "execute_eval_campaign" not in workflow and "--execute" not in workflow
    assert "${{ inputs.candidate_sha }}" not in workflow.split("steps:", 1)[1]
    parsed = yaml.load(workflow, Loader=yaml.BaseLoader)
    assert set(parsed["on"]) == {"workflow_dispatch"}
    assert parsed["on"]["workflow_dispatch"]["inputs"]["check_only"]["default"] == "false"
    job = parsed["jobs"]["publish-evals"]
    assert "RAILWAY_TOKEN" not in job["env"]
    assert job["steps"][-1]["env"]["EVAL_DEPLOY_CHECK_ONLY"] == "${{ inputs.check_only }}"
    assert job["runs-on"] == "ubuntu-24.04"
    for step in job["steps"]:
        if "uses" in step:
            assert len(step["uses"].split("@")[1]) == 40


def test_workflow_temp_directory_uses_runtime_environment_not_job_runner_context():
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/deploy-evals.yml"
                ).read_text(encoding="utf-8")
    job = yaml.load(workflow, Loader=yaml.BaseLoader)["jobs"]["publish-evals"]
    # YAML parsing alone cannot detect GitHub's context-availability restrictions:
    # jobs.<job_id>.env has no runner context, unlike step env/run expressions.
    assert all("runner." not in value for value in job["env"].values())
    commands = [step["run"] for step in job["steps"]
                if step.get("run", "").startswith("python scripts/deploy_eval_candidate.py")
                and not step["run"].endswith(" check-cli")]
    assert len(commands) == 2
    assert all('--directory "$RUNNER_TEMP/eval-candidate"' in command for command in commands)


def test_ci_job_pagination_does_not_accept_hidden_required_jobs(monkeypatch):
    run = {"id": 123, "run_number": 1, "run_attempt": 3, "head_sha": COMMIT,
           "head_branch": "main", "event": "push", "status": "completed",
           "conclusion": "success"}
    calls = []
    def github(path, _):
        calls.append(path)
        if "ci.yml/runs" in path:
            return {"workflow_runs": [run]}
        if path.endswith("&page=1"):
            return {"jobs": [{"name": str(i), "conclusion": "success", "status": "completed"}
                             for i in range(100)]}
        return {"jobs": [{"name": n, "conclusion": "success", "status": "completed"}
                         for n in ("quality", "integration", "collector-config")]}
    monkeypatch.setattr(deploy, "github_get", github)
    assert deploy.ci_gate(COMMIT, "synthetic")["ci_run_id"] == 123
    assert "page=2" in calls[-1]


def test_no_matching_ci_of_main_is_blocked(monkeypatch):
    monkeypatch.setattr(deploy, "github_get", lambda *_: {"workflow_runs": [{
        "head_sha": "b" * 40, "head_branch": "main", "event": "push",
    }]})
    with pytest.raises(ValueError, match="ci_missing"):
        deploy.ci_gate(COMMIT, "synthetic")


def test_other_deployment_change_is_not_claimed_success(candidate, status, env):
    railway = FakeRailway(status, candidate[1])
    original = railway.status
    calls = []
    def inventory():
        value = original()
        if calls:
            value["environments"]["edges"][0]["node"]["serviceInstances"]["edges"][1][
                "node"]["latestDeployment"]["id"] = "concurrent-unrelated-deploy"
        calls.append(True)
        return value
    railway.status = inventory
    with pytest.raises(ValueError, match="other_services_changed"):
        deploy.publish(candidate[0], env, railway, {})


def test_running_proof_and_exact_id_required(candidate, status, env, monkeypatch):
    railway = FakeRailway(status, candidate[1])
    environment = railway.value["environments"]["edges"][0]["node"]
    latest = environment["serviceInstances"]["edges"][0]["node"]["latestDeployment"]
    latest["instances"] = [{"status": "CRASHED"}]
    clock = iter([0, 0, 100])
    monkeypatch.setattr(deploy.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(deploy.time, "sleep", lambda _: None)
    with pytest.raises(TimeoutError):
        deploy.publish(candidate[0], env, railway, {}, wait_seconds=1)
    latest["id"] = "some-other-deployment"
    clock = iter([0, 0])
    with pytest.raises(ValueError, match="superseded"):
        deploy.publish(candidate[0], env, railway, {}, wait_seconds=1)


def test_main_failure_summary_has_no_raw_provider_text_or_secret(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(deploy, "prepare", Mock(side_effect=RuntimeError("SECRET_PROVIDER_DATA")))
    assert deploy.main(["prepare", "--sha", COMMIT, "--directory", str(tmp_path / "out")]) == 1
    assert "SECRET" not in capsys.readouterr().out
    assert "SECRET" not in summary.read_text(encoding="utf-8")


def test_github_request_fixed_origin_header_and_no_mutation(monkeypatch):
    response = io.BytesIO(b'{"workflow_runs": []}')
    request = Mock(return_value=response)
    monkeypatch.setattr(deploy.urllib.request, "urlopen", request)
    assert deploy.github_get("/actions/workflows/ci.yml/runs", "synthetic") == {
        "workflow_runs": [],
    }
    sent = request.call_args.args[0]
    assert sent.full_url == "https://api.github.com/repos/" + deploy.REPO + (
        "/actions/workflows/ci.yml/runs"
    )
    assert sent.get_method() == "GET" and sent.get_header("Authorization") == "Bearer synthetic"


def test_ci_for_control_code_also_required_before_artifact_write(
    candidate, env, monkeypatch, tmp_path,
):
    env["GITHUB_SHA"] = "b" * 40
    monkeypatch.setattr(deploy, "git", lambda *_: b"")
    calls = []
    def ci(sha, _token):
        calls.append(sha)
        if sha != COMMIT:
            raise ValueError("eval_deploy_latest_ci_not_successful")
        return {"ci_run_id": 123, "ci_attempt": 1}
    monkeypatch.setattr(deploy, "ci_gate", ci)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="ci_not_successful"):
        deploy.prepare(tmp_path, COMMIT, output, env)
    assert calls == [COMMIT, "b" * 40] and not output.exists()


def test_candidate_metadata_does_not_echo_extra_artifact_data(candidate):
    metadata = {**candidate[1], "PRIVATE_TOKEN": "private-not-reportable"}
    value = deploy.candidate_metadata(metadata)
    assert "PRIVATE_TOKEN" not in value
    metadata["ci_run_id"] = "private-not-an-id"
    with pytest.raises(ValueError, match="invalid_candidate_metadata"):
        deploy.candidate_metadata(metadata)


def test_missing_environment_secret_blocks_before_cli(monkeypatch):
    monkeypatch.setattr(deploy.shutil, "which", Mock(
        side_effect=AssertionError("no local install"),
    ))
    with pytest.raises(ValueError, match="remote_linux_token_required"):
        deploy.Railway("")
