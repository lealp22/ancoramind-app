"""Recovery uses explicit configuration, never a default or a live local CLI."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from scripts import deploy_eval_candidate as deploy
from tests.unit import test_deploy_eval_candidate as publication

publication_candidate = publication.candidate
publication_env = publication.env


@pytest.fixture
def recovery_status():
    fixture = Path(__file__).parent / "fixtures/railway_eval_inventory.json"
    value = json.loads(fixture.read_text(encoding="utf-8"))["status"]
    node = next(e["node"] for e in value["environments"]["edges"][0]["node"][
        "serviceInstances"]["edges"] if e["node"]["serviceId"] == deploy.SERVICE)
    node.update(latestDeployment=None, activeDeployments=[], numReplicas=None)
    return value


@pytest.fixture
def config_response():
    # Synthetic additions prove that the scalar blob never reaches reports/projection.
    return {"data": {"environment": {"id": deploy.ENVIRONMENT, "projectId": deploy.PROJECT,
            "config": {"sharedVariables": {"private": "SYNTHETIC_PRIVATE"}, "services": {
                "other": {"variables": {"secret": "SYNTHETIC_PRIVATE"}},
                deploy.SERVICE: {
                    "deploy": {"startCommand": "python /app/scripts/eval_service.py",
                               "multiRegionConfig": {"europe-west4-drams3a": {"numReplicas": 1}}},
                    "volumeMounts": {deploy.VOLUME: {"mountPath": "/eval-state"}},
                    "variables": {"secret": "SYNTHETIC_PRIVATE"},
                },
            }}}}}


def recovery_node(status):
    return next(e["node"] for e in status["environments"]["edges"][0]["node"][
        "serviceInstances"]["edges"] if e["node"]["serviceId"] == deploy.SERVICE)


def test_reproduce_no_deployment_blocks_without_explicit_configuration(recovery_status):
    with pytest.raises(ValueError, match="recovery_configuration_unavailable"):
        deploy.inventory(recovery_status)


@pytest.mark.parametrize("check_only", [True, False])
def test_real_adapter_recovers_same_service_once_and_verifies_exact_idle_deployment(
    monkeypatch, recovery_status, config_response, publication_candidate, publication_env,
    check_only, capsys,
):
    candidate, env = publication_candidate, publication_env
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    node = recovery_node(recovery_status)
    calls = []
    deployment = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    def run(argv, **kwargs):
        assert kwargs["env"]["RAILWAY_TOKEN"] == "synthetic"
        args = argv[1:]
        calls.append(args)
        if args == ["--version"]:
            result = "railway " + deploy.CLI_VERSION
        elif args[0] == "status":
            result = json.dumps(recovery_status)
        elif args[0] == "api":
            assert args[1].startswith("query {") and "mutation" not in args[1]
            if "config(" in args[1]:
                assert 'projectId: "' + deploy.PROJECT in args[1]
                assert "decryptVariables: false" in args[1]
                result = json.dumps(config_response)
            else:
                result = json.dumps({"data": {
                    "environmentStagedChanges": {"id": "<empty>", "status": "STAGED",
                                                 "environmentId": deploy.ENVIRONMENT, "patch": {}},
                    "environmentPendingWork": [],
                }})
        elif args[0] == "variable":
            assert not check_only and "--skip-deploys" in args
            result = "updated"
        elif args[0] == "up":
            assert not check_only and "--path-as-root" in args
            assert kwargs["cwd"] == candidate[0] / "context"
            node["latestDeployment"] = {"id": deployment, "status": "SUCCESS",
                                        "instances": [{"status": "RUNNING"}], "meta": {
                "serviceManifest": {"deploy": {"multiRegionConfig": {
                    "europe-west4-drams3a": {"numReplicas": 1},
                }}},
            }}
            result = json.dumps({"deploymentId": deployment})
        elif args[0] == "deployment":
            result = json.dumps([{"id": deployment, "status": "SUCCESS"}])
        elif args[0] == "logs":
            result = json.dumps({"status": "idle_manual_only", "inference_started": False,
                                 "code_sha": candidate[1]["code_sha"], "worktree": "clean",
                                 "identity_source": "sealed_image",
                                 "source_fingerprint": candidate[1]["source_fingerprint"]})
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(argv, 0, stdout=result, stderr="")
    monkeypatch.setattr(deploy.subprocess, "run", run)
    report = deploy.publish(candidate[0], env, deploy.Railway("synthetic"), {},
                            check_only=check_only)
    assert report["replica_evidence"] == "live_configuration_single_region_no_deployment"
    assert report["status"] == ("preflight_verified_no_upload" if check_only
                                else "deployed_idle_verified")
    assert sum(args[0] == "up" for args in calls) == (0 if check_only else 1)
    assert sum(args[0] == "variable" for args in calls) == (0 if check_only else 1)
    assert sum(args[0] == "api" and "config(" in args[1] for args in calls) == 1
    assert sum(args[0] == "api" and "environmentPendingWork" in args[1]
               for args in calls) == (1 if check_only else 2)
    assert "SYNTHETIC_PRIVATE" not in json.dumps(report) + capsys.readouterr().out
    assert "variables" not in json.dumps(deploy.recovery_configuration(config_response)).lower()


@pytest.mark.parametrize("change", [
    "errors", "data_missing", "environment_missing", "wrong_project", "wrong_environment",
    "config_missing", "config_string", "services_missing", "service_missing", "deploy_missing",
])
def test_configuration_response_incomplete_never_proves_recovery(config_response, change):
    environment = config_response["data"]["environment"]
    if change == "errors":
        config_response["errors"] = [{"message": "SYNTHETIC_PRIVATE"}]
    elif change == "data_missing":
        del config_response["data"]
    elif change == "environment_missing":
        del config_response["data"]["environment"]
    elif change == "wrong_project":
        environment["projectId"] = "other"
    elif change == "wrong_environment":
        environment["id"] = "other"
    elif change == "config_missing":
        del environment["config"]
    elif change == "config_string":
        environment["config"] = "SYNTHETIC_PRIVATE"
    elif change == "services_missing":
        del environment["config"]["services"]
    elif change == "service_missing":
        del environment["config"]["services"][deploy.SERVICE]
    else:
        del environment["config"]["services"][deploy.SERVICE]["deploy"]
    with pytest.raises(ValueError, match="recovery_configuration_unavailable") as error:
        deploy.recovery_configuration(config_response)
    assert "SYNTHETIC_PRIVATE" not in str(error.value)


@pytest.mark.parametrize("change", [
    "regions_missing", "regions_null", "regions_empty", "regions_multiple", "count_missing",
    "count_null", "count_bool", "count_string", "count_two", "legacy_two", "legacy_missing",
    "start_missing", "start_wrong", "mount_missing", "mount_wrong", "mount_extra",
    "deleted", "created", "active_missing", "active_null", "active_running",
    "latest_missing", "latest_empty", "latest_unknown",
])
def test_unknown_or_contradictory_recovery_blocks_before_mutation(
    recovery_status, config_response, change, publication_candidate, publication_env,
):
    node = recovery_node(recovery_status)
    config = deploy.recovery_configuration(config_response)
    node["_eval_recovery_config"] = config
    settings = config["deploy"]
    regions = settings["multiRegionConfig"]
    region = next(iter(regions.values()))
    if change == "regions_missing":
        del settings["multiRegionConfig"]
    elif change in {"regions_null", "regions_empty"}:
        settings["multiRegionConfig"] = None if change.endswith("null") else {}
    elif change == "regions_multiple":
        regions["other"] = {"numReplicas": 1}
    elif change == "count_missing":
        del region["numReplicas"]
    elif change.startswith("count_"):
        region["numReplicas"] = {"count_null": None, "count_bool": True,
                                 "count_string": "1", "count_two": 2}[change]
    elif change == "legacy_two":
        node["numReplicas"] = 2
    elif change == "legacy_missing":
        del node["numReplicas"]
    elif change == "start_missing":
        del settings["startCommand"]
    elif change == "start_wrong":
        settings["startCommand"] = "SYNTHETIC_PRIVATE"
    elif change == "mount_missing":
        del config["volumeMounts"]
    elif change == "mount_wrong":
        config["volumeMounts"][deploy.VOLUME]["mountPath"] = "SYNTHETIC_PRIVATE"
    elif change == "mount_extra":
        config["volumeMounts"]["other"] = {"mountPath": "/data"}
    elif change in {"deleted", "created"}:
        config["isDeleted" if change == "deleted" else "isCreated"] = True
    elif change == "active_missing":
        del node["activeDeployments"]
    elif change == "active_null":
        node["activeDeployments"] = None
    elif change == "active_running":
        node["activeDeployments"] = [{"status": "SUCCESS"}]
    elif change == "latest_missing":
        del node["latestDeployment"]
    elif change == "latest_empty":
        node["latestDeployment"] = {}
    else:
        node["latestDeployment"] = {"status": "SYNTHETIC_PRIVATE"}
    railway = publication.FakeRailway(recovery_status, publication_candidate[1])
    with pytest.raises(ValueError, match="eval_deploy_") as error:
        deploy.publish(publication_candidate[0], publication_env, railway, {})
    assert "SYNTHETIC_PRIVATE" not in str(error.value)
    assert not any(args[0] in {"variable", "up"} for args in railway.calls)


@pytest.mark.parametrize("command,phase", [
    (["--version"], "cli_version"), (["status"], "inventory"),
    (["api"], "api_query"), (["variable"], "metadata_variables"), (["up"], "upload"),
    (["deployment"], "deployment_poll"), (["logs"], "idle_identity_logs"),
])
@pytest.mark.parametrize("failure", ["exit", "timeout", "unavailable"])
def test_command_failure_reports_only_safe_phase_and_exit_code(
    monkeypatch, tmp_path, capsys, command, phase, failure,
):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    run = Mock()
    if failure == "exit":
        run.return_value = subprocess.CompletedProcess([], 127, stdout="SYNTHETIC_PRIVATE",
                                                       stderr="SYNTHETIC_PRIVATE")
    elif failure == "timeout":
        run.side_effect = subprocess.TimeoutExpired("SYNTHETIC_PRIVATE", 180,
                                                    output="SYNTHETIC_PRIVATE")
    else:
        run.side_effect = OSError("SYNTHETIC_PRIVATE")
    monkeypatch.setattr(deploy.subprocess, "run", run)
    monkeypatch.setenv("RAILWAY_TOKEN", "synthetic")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    def publish(*args, **kwargs):
        deploy.Railway("synthetic").call(command)
    monkeypatch.setattr(deploy, "publish", publish)
    assert deploy.main(["publish", "--directory", str(tmp_path)]) == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["phase"] == phase
    assert report["command_exit_code"] == (127 if failure == "exit" else None)
    assert run.call_count == 1
    assert "SYNTHETIC_PRIVATE" not in output.out + output.err + summary.read_text(encoding="utf-8")


def test_cli_probe_has_no_token_or_remote_call(monkeypatch, publication_env, capsys):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    for key, value in publication_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("RAILWAY_TOKEN", "PRIVATE_NOT_FOR_PROBE")
    monkeypatch.setenv("RAILWAY_API_TOKEN", "PRIVATE_NOT_FOR_PROBE")
    run = Mock(return_value=subprocess.CompletedProcess([], 0,
               stdout="railway " + deploy.CLI_VERSION, stderr=""))
    monkeypatch.setattr(deploy.subprocess, "run", run)
    assert deploy.main(["check-cli"]) == 0
    assert "cli_verified_without_token" in capsys.readouterr().out
    assert run.call_args.args[0] == ["/runner/railway", "--version"]
    assert not any("TOKEN" in key for key in run.call_args.kwargs["env"])
    with pytest.raises(ValueError, match="token_required"):
        deploy.Railway(None).call(["status"])
    assert run.call_count == 1


def test_workflow_probes_before_secret_and_only_allows_pinned_downloader():
    workflow = deploy.ROOT / ".github/workflows/deploy-evals.yml"
    steps = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)[
        "jobs"]["publish-evals"]["steps"]
    install = next(i for i, step in enumerate(steps) if "npm install" in step.get("run", ""))
    probe = next(i for i, step in enumerate(steps) if step.get("run", "").endswith(" check-cli"))
    secret = next(i for i, step in enumerate(steps) if "RAILWAY_TOKEN" in step.get("env", {}))
    assert install < probe < secret
    assert "--allow-scripts=@railway/cli@" + deploy.CLI_VERSION in steps[install]["run"]
    assert "dangerously" not in steps[install]["run"]
    assert "env" not in steps[probe] and "env" not in steps[install]


@pytest.mark.parametrize("blocked_pending", [True, False])
def test_pending_guard_or_unreadable_config_prevents_any_recovery_mutation(
    monkeypatch, recovery_status, publication_candidate, publication_env, blocked_pending,
):
    monkeypatch.setattr(deploy.sys, "platform", "linux")
    monkeypatch.setattr(deploy.shutil, "which", lambda _: "/runner/railway")
    calls = []
    def run(argv, **kwargs):
        args = argv[1:]
        calls.append(args)
        if args == ["--version"]:
            output = "railway " + deploy.CLI_VERSION
        elif args[0] == "status":
            output = json.dumps(recovery_status)
        elif args[0] == "api" and "config(" not in args[1]:
            output = json.dumps({"data": {"environmentPendingWork": [],
                "environmentStagedChanges": {"id": "<empty>", "status": "STAGED",
                    "environmentId": deploy.ENVIRONMENT,
                    "patch": {"PRIVATE": "SYNTHETIC_PRIVATE"} if blocked_pending else {}}}})
        elif args[0] == "api":
            output = json.dumps({"errors": [{"message": "SYNTHETIC_PRIVATE"}]})
        else:
            raise AssertionError("Unexpected mutation")
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")
    monkeypatch.setattr(deploy.subprocess, "run", run)
    with pytest.raises(ValueError, match="eval_deploy_") as error:
        deploy.publish(publication_candidate[0], publication_env, deploy.Railway("synthetic"), {})
    assert "SYNTHETIC_PRIVATE" not in str(error.value)
    assert not any(args[0] in {"variable", "up"} for args in calls)
    assert sum(args[0] == "api" and "config(" in args[1]
               for args in calls) == (0 if blocked_pending else 1)


def test_no_deployment_after_upload_cannot_be_verified_as_success(
    recovery_status, config_response, publication_candidate, publication_env, monkeypatch,
):
    node = recovery_node(recovery_status)
    node["_eval_recovery_config"] = deploy.recovery_configuration(config_response)
    railway = publication.FakeRailway(recovery_status, publication_candidate[1])
    with pytest.raises(ValueError, match="superseded"):
        deploy.publish(publication_candidate[0], publication_env, railway, {})
    assert sum(args[0] == "up" for args in railway.calls) == 1
    assert not any(args[0] == "logs" for args in railway.calls)


@pytest.mark.parametrize("platform,hosted", [("win32", "github-hosted"), ("linux", "self-hosted")])
def test_credential_free_probe_never_runs_cli_locally(monkeypatch, platform, hosted):
    monkeypatch.setattr(deploy.sys, "platform", platform)
    monkeypatch.setenv("RUNNER_ENVIRONMENT", hosted)
    runner = Mock(side_effect=AssertionError("No CLI allowed"))
    monkeypatch.setattr(deploy.subprocess, "run", runner)
    monkeypatch.setattr(deploy.shutil, "which", runner)
    with pytest.raises(ValueError, match="remote_linux_token_required"):
        deploy.Railway(None)
    runner.assert_not_called()
