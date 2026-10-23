"""Manual GitHub-hosted publication of one eval candidate; no local CLI install.

Only stdlib and trusted packaging helpers. Never executes candidate Python,
installs its dependencies, reads eval-state or grants model execution permission.
CLI raw output stays private in memory: public summaries contain allowlisted metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_source import source_fingerprint  # noqa: E402
from scripts.prepare_eval_build import _include, package_archive  # noqa: E402

REPO = "lealp22/ancoramind-app"
PROJECT = "b291bc34-c75d-4a8a-9f82-d3d7cf32aeef"
ENVIRONMENT = "79202202-e66e-4778-8ce3-6aa975c212d5"
SERVICE = "79f8f0c2-1ba1-4fea-9e89-d4b672b23efc"
VOLUME = "b88f8940-dd92-430f-8d6f-a4adb2b455c8"
CLI_VERSION = "5.70.0"
TARGET = ["--project", PROJECT, "--environment", ENVIRONMENT]
SERVICE_TARGET = [*TARGET, "--service", SERVICE]
SHA = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def validate_dispatch(sha: str, env: dict[str, str]) -> None:
    if (not SHA.fullmatch(sha) or env.get("GITHUB_REPOSITORY") != REPO
        or env.get("GITHUB_REF") != "refs/heads/main"
        or env.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or env.get("EVAL_CONFIRM_IDLE") != "true"
        or env.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        raise ValueError("eval_deploy_manual_main_sha_idle_and_hosted_runner_required")
    if "RAILWAY_TOKEN" in env and not env["RAILWAY_TOKEN"]:
        raise ValueError("eval_deploy_github_environment_secret_missing")


def github_get(path: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        "https://api.github.com/repos/" + REPO + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "ancoramind-eval-deploy"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # fixed GitHub origin
        return json.load(response)


def ci_gate(sha: str, token: str) -> dict[str, Any]:
    if not SHA.fullmatch(sha) or not token:
        raise ValueError("eval_deploy_ci_auth_or_sha_required")
    runs = github_get(
        f"/actions/workflows/ci.yml/runs?head_sha={sha}&event=push&per_page=100", token,
    )
    selected = [run for run in runs["workflow_runs"] if run.get("head_sha") == sha
                and run.get("event") == "push" and run.get("head_branch") == "main"]
    if runs.get("total_count", 0) > 100:
        raise ValueError("eval_deploy_ci_run_limit_exceeded")
    if not selected:
        raise ValueError("eval_deploy_ci_missing")
    latest = max(selected, key=lambda run: (run["run_number"], run.get("run_attempt", 1)))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise ValueError("eval_deploy_latest_ci_not_successful")
    run_id, attempt = int(latest["id"]), int(latest["run_attempt"])
    jobs = []
    for page in range(1, 11):
        batch = github_get(
            f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}", token,
        )["jobs"]
        jobs.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise ValueError("eval_deploy_ci_job_pagination_exceeded")
    for name in ("quality", "integration", "collector-config"):
        matching = [job for job in jobs if job.get("name") == name]
        if (len(matching) != 1 or matching[0].get("conclusion") != "success"
            or matching[0].get("status") != "completed"):
            raise ValueError("eval_deploy_ci_required_job_not_successful")
    return {"ci_run_id": run_id, "ci_attempt": attempt,
            "ci_url": f"https://github.com/{REPO}/actions/runs/{run_id}"}


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True, timeout=60)
    return result.stdout


def unpack(payload: bytes, folder: Path, mode: str) -> None:
    """No extractall/traversal/links; generated package or allowlisted git archive."""
    with tarfile.open(fileobj=io.BytesIO(payload), mode=mode) as archive:
        seen = set()
        for member in archive:
            if member.isdir():
                continue
            if mode == "r:" and not _include(member.name):
                continue
            if (not member.isfile() or member.name in seen or "\\" in member.name
                or Path(member.name).is_absolute() or ".." in Path(member.name).parts):
                raise ValueError("eval_deploy_package_unsafe")
            seen.add(member.name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("eval_deploy_package_invalid")
            path = folder / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(stream.read())


def prepare(root: Path, sha: str, destination: Path, env: dict[str, str]) -> dict[str, Any]:
    validate_dispatch(sha, env)
    if not destination.is_absolute() or destination.exists():
        raise ValueError("eval_deploy_new_absolute_output_required")
    git(root, "merge-base", "--is-ancestor", sha, "origin/main")
    # A protected main may advance during a run; never choose latest implicitly.
    ci = ci_gate(sha, env.get("GH_TOKEN", ""))
    control_sha = env.get("GITHUB_SHA", "")
    if not SHA.fullmatch(control_sha):
        raise ValueError("eval_deploy_control_revision_required")
    if control_sha != sha:
        ci_gate(control_sha, env.get("GH_TOKEN", ""))
    raw = git(root, "archive", "--format=tar", sha)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary)
        unpack(raw, source, "r:")
        fingerprint = source_fingerprint(source)
        payload = package_archive(raw, fingerprint)
    destination.mkdir(mode=0o700)
    context = destination / "context"
    context.mkdir(mode=0o700)
    unpack(payload, context, "r:gz")
    metadata = {"schema_version": 1, "code_sha": sha, "source_fingerprint": fingerprint,
                "prepared_archive_sha256": hashlib.sha256(payload).hexdigest(), **ci,
                "publication_code_sha": control_sha,
                "status": "prepared_no_upload", "inference_started": False}
    (destination / "candidate.json").write_text(json.dumps(metadata), encoding="utf-8")
    return metadata


class RailwayCommandError(ValueError):
    """Only fixed phase labels and numeric exit status may leave the CLI boundary."""

    def __init__(self, phase: str, exit_code: int | None, failure: str = "failed"):
        super().__init__("eval_deploy_railway_command_" + failure)
        self.phase = phase
        self.exit_code = exit_code


class Railway:
    """Explicit targets on every command. No local linking or credential listing."""

    def __init__(self, token: str | None):
        # None is the credential-free version probe, never an authenticated adapter.
        if (sys.platform != "linux" or token == ""
            or (token is None and os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted")):
            raise ValueError("eval_deploy_remote_linux_token_required")
        binary = shutil.which("railway")
        if binary is None:
            raise ValueError("eval_deploy_runner_cli_missing")
        self.binary = binary
        self.env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR") if key in os.environ}
        self.env.update(CI="true", NO_COLOR="1")
        if token is not None:
            self.env["RAILWAY_TOKEN"] = token

    def call(self, args: list[str], *, cwd: Path | None = None, phase: str | None = None) -> str:
        labels = {"--version": "cli_version", "status": "inventory", "api": "api_query",
                  "variable": "metadata_variables", "up": "upload",
                  "deployment": "deployment_poll", "logs": "idle_identity_logs"}
        label = phase or labels.get(args[0], "unknown_command")
        if label not in {*labels.values(), "pending_work", "recovery_configuration"}:
            raise ValueError("eval_deploy_invalid_command_phase")
        if "RAILWAY_TOKEN" not in self.env and args != ["--version"]:
            raise ValueError("eval_deploy_remote_linux_token_required")
        try:
            process = subprocess.run([self.binary, *args], env=self.env, cwd=cwd,
                                     capture_output=True, text=True, timeout=180, check=False)
        except subprocess.TimeoutExpired:
            raise RailwayCommandError(label, None, "timeout") from None
        except OSError:
            raise RailwayCommandError(label, None, "unavailable") from None
        if process.returncode:
            # Do not leak CLI/GraphQL exception text, values or arbitrary container logs.
            raise RailwayCommandError(label, process.returncode)
        return process.stdout

    def status(self) -> dict[str, Any]:
        value = json.loads(self.call(["status", *TARGET, "--json"]))
        # Railway returns a non-null object: a draft or the <empty> sentinel.
        # Patch contents stay in memory only; never include them in reports or errors.
        query = ('query { environmentStagedChanges(environmentId: "' + ENVIRONMENT
                 + '") { id status environmentId patch } '
                 + 'environmentPendingWork(environmentId: "' + ENVIRONMENT
                 + '") { id kind status environmentId children { id } } }')
        validate_pending_work(json.loads(self.call(["api", query], phase="pending_work")))
        environments = [edge["node"] for edge in value["environments"]["edges"]
                        if edge["node"]["id"] == ENVIRONMENT]
        if value.get("id") == PROJECT and len(environments) == 1:
            candidates = [edge["node"] for edge in environments[0]["serviceInstances"]["edges"]
                          if edge["node"]["serviceId"] == SERVICE]
            if (len(candidates) == 1 and "latestDeployment" in candidates[0]
                and candidates[0]["latestDeployment"] is None):
                # The API exposes configuration as a scalar blob. Never decrypt,
                # print, persist or return variables/other services from that blob.
                query = ('query { environment(id: "' + ENVIRONMENT + '", projectId: "'
                         + PROJECT + '") { id projectId config(decryptVariables: false) } }')
                response = json.loads(self.call(["api", query], phase="recovery_configuration"))
                candidates[0]["_eval_recovery_config"] = recovery_configuration(response)
        return value


def recovery_configuration(response: Any) -> dict[str, Any]:
    """Project only non-secret evidence from live configuration; no staged overlay."""
    if (not isinstance(response, dict) or response.get("errors")
        or not isinstance(response.get("data"), dict)):
        raise ValueError("eval_deploy_recovery_configuration_unavailable")
    environment = response["data"].get("environment")
    if (not isinstance(environment, dict) or environment.get("id") != ENVIRONMENT
        or environment.get("projectId") != PROJECT
        or not isinstance(environment.get("config"), dict)):
        raise ValueError("eval_deploy_recovery_configuration_unavailable")
    services = environment["config"].get("services")
    service = services.get(SERVICE) if isinstance(services, dict) else None
    if not isinstance(service, dict) or not isinstance(service.get("deploy"), dict):
        raise ValueError("eval_deploy_recovery_configuration_unavailable")
    return {"deploy": {key: service["deploy"][key]
                       for key in ("startCommand", "multiRegionConfig")
                       if key in service["deploy"]},
            **{key: service[key] for key in ("volumeMounts", "isCreated", "isDeleted")
               if key in service}}


def recovery_replica_evidence(candidate: dict[str, Any]) -> str:
    """No deployment is recoverable only with explicit live settings and no active work."""
    if candidate.get("activeDeployments") != []:
        raise ValueError("eval_deploy_existing_deployment_in_progress_or_unknown")
    config = candidate.get("_eval_recovery_config")
    if not isinstance(config, dict) or not isinstance(config.get("deploy"), dict):
        raise ValueError("eval_deploy_recovery_configuration_unavailable")
    if any(key in config and config[key] is not False for key in ("isCreated", "isDeleted")):
        raise ValueError("eval_deploy_recovery_configuration_unavailable")
    deploy = config["deploy"]
    if deploy.get("startCommand") != "python /app/scripts/eval_service.py":
        raise ValueError("eval_deploy_start_command_drift")
    if config.get("volumeMounts") != {VOLUME: {"mountPath": "/eval-state"}}:
        raise ValueError("eval_deploy_volume_drift")
    regions = deploy.get("multiRegionConfig")
    if (not isinstance(regions, dict) or len(regions) != 1
        or not all(isinstance(region, str) and region for region in regions)
        or not all(isinstance(row, dict) and type(row.get("numReplicas")) is int
                   and row["numReplicas"] == 1 for row in regions.values())):
        raise ValueError("eval_deploy_replica_configuration_drift")
    return "live_configuration_single_region_no_deployment"


def validate_pending_work(response: Any) -> None:
    """Verify an empty draft or the exact no-draft sentinel against pending work."""
    if (not isinstance(response, dict) or response.get("errors")
        or not isinstance(response.get("data"), dict)):
        raise ValueError("eval_deploy_pending_work_cannot_be_verified")
    data = response["data"]
    staged, pending = data.get("environmentStagedChanges"), data.get("environmentPendingWork")
    if (not isinstance(staged, dict) or not isinstance(staged.get("id"), str)
        or staged.get("environmentId") != ENVIRONMENT
        or not isinstance(pending, list)):
        raise ValueError("eval_deploy_pending_work_cannot_be_verified")
    if (staged.get("status") != "STAGED" or type(staged.get("patch")) is not dict
        or staged["patch"] != {}):
        raise ValueError("eval_deploy_pending_changes_or_wrong_environment")
    # After committing without a deploy, the API uses this literal sentinel,
    # not null or an omitted draft. No actual pending row may accompany it.
    if staged["id"] == "<empty>":
        if pending != []:
            raise ValueError("eval_deploy_pending_work_cannot_be_verified")
        return
    if not UUID.fullmatch(staged["id"]):
        raise ValueError("eval_deploy_pending_work_cannot_be_verified")
    # A persisted draft still requires its matching row; an empty list alone
    # never proves consistency. Any other operation or child blocks upload.
    expected = {"id": "patch:" + staged["id"], "kind": "EnvironmentPatch", "status": "staged",
                "environmentId": ENVIRONMENT, "children": []}
    if pending != [expected]:
        raise ValueError("eval_deploy_pending_work_cannot_be_verified")


def single_replica_evidence(candidate: dict[str, Any]) -> str:
    """Use explicit manifest regions before the nullable legacy per-region field.

    Mirrors CLI5.70.0 service_summary.rs/regions.rs, but never defaults unknown to 1.
    Deployment metadata stays private; only a fixed evidence label is reportable.
    """
    legacy = candidate.get("numReplicas")
    if "numReplicas" not in candidate or (
        legacy is not None and (type(legacy) is not int or legacy != 1)
    ):
        raise ValueError("eval_deploy_replica_configuration_drift")
    if "latestDeployment" in candidate and candidate["latestDeployment"] is None:
        return recovery_replica_evidence(candidate)
    meta = (candidate.get("latestDeployment") or {}).get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            raise ValueError("eval_deploy_replica_evidence_unavailable")
        manifest = meta.get("serviceManifest")
        if manifest is not None and not isinstance(manifest, dict):
            raise ValueError("eval_deploy_replica_evidence_unavailable")
        config = (manifest or {}).get("deploy")
        if config is not None:
            if not isinstance(config, dict):
                raise ValueError("eval_deploy_replica_evidence_unavailable")
            if "multiRegionConfig" in config:
                regions = config["multiRegionConfig"]
                if (not isinstance(regions, dict) or len(regions) != 1
                    or not all(isinstance(region, str) and region for region in regions)
                    or not all(isinstance(row, dict) and type(row.get("numReplicas")) is int
                               and row["numReplicas"] == 1 for row in regions.values())):
                    raise ValueError("eval_deploy_replica_configuration_drift")
                return "deployment_manifest_single_region"
            if "numReplicas" in config:
                if type(config["numReplicas"]) is not int or config["numReplicas"] != 1:
                    raise ValueError("eval_deploy_replica_configuration_drift")
                return "deployment_manifest_explicit_count"
    if legacy == 1:
        return "legacy_explicit_count"
    raise ValueError("eval_deploy_replica_evidence_unavailable")


def inventory(value: dict[str, Any]) -> tuple[dict[str, str | None], dict[str, Any]]:
    if value.get("id") != PROJECT:
        raise ValueError("eval_deploy_wrong_project")
    environments = [e["node"] for e in value["environments"]["edges"]
                    if e["node"]["id"] == ENVIRONMENT]
    if len(environments) != 1 or "unmergedChangesCount" not in environments[0]:
        raise ValueError("eval_deploy_pending_changes_or_wrong_environment")
    environment = environments[0]
    # Nullable merge-comparison metadata is not the staged-work signal: production
    # returns null. Railway.status() independently verifies an exactly empty draft.
    count = environment["unmergedChangesCount"]
    if count is not None and (type(count) is not int or count != 0):
        raise ValueError("eval_deploy_pending_changes_or_wrong_environment")
    services = {e["node"]["serviceId"]: e["node"]
                for e in environment["serviceInstances"]["edges"]}
    candidate = services.get(SERVICE, {})
    volume = [v["node"] for v in environment["volumeInstances"]["edges"]
              if v["node"]["volume"]["id"] == VOLUME]
    if candidate.get("serviceName") != "ancoramind-evals":
        raise ValueError("eval_deploy_service_identity_drift")
    if candidate.get("startCommand") != "python /app/scripts/eval_service.py":
        raise ValueError("eval_deploy_start_command_drift")
    single_replica_evidence(candidate)
    domains = candidate.get("domains")
    if ("cronSchedule" not in candidate or candidate["cronSchedule"] is not None
        or candidate.get("tracingEnabled") is not False
        or candidate.get("autoInstrumentationEnabled") is not False
        or not isinstance(domains, dict)
        or domains.get("serviceDomains") != [] or domains.get("customDomains") != []):
        raise ValueError("eval_deploy_exposure_schedule_or_tracing_drift")
    if (len(volume) != 1 or volume[0].get("serviceId") != SERVICE
        or volume[0].get("mountPath") != "/eval-state"
        or "deletedAt" not in volume[0] or volume[0]["deletedAt"] is not None
        or volume[0].get("isPendingDeletion") is not False):
        raise ValueError("eval_deploy_volume_drift")
    latest_status = (candidate.get("latestDeployment") or {}).get("status")
    no_deployment = "latestDeployment" in candidate and candidate["latestDeployment"] is None
    if not no_deployment and latest_status not in {
        "SUCCESS", "FAILED", "CRASHED", "REMOVED", "STOPPED",
    }:
        raise ValueError("eval_deploy_existing_deployment_in_progress_or_unknown")
    other = {service_id: (node.get("latestDeployment") or {}).get("id")
             for service_id, node in services.items() if service_id != SERVICE}
    return other, candidate


def idle_log(text: str, sha: str, fingerprint: str) -> bool:
    for line in text.splitlines():
        try:
            row = json.loads(line)
            if isinstance(row.get("message"), str) and row["message"].startswith("{"):
                row = json.loads(row["message"])
            if (row.get("status") == "idle_manual_only" and row.get("code_sha") == sha
                and row.get("source_fingerprint") == fingerprint
                and row.get("inference_started") is False and row.get("worktree") == "clean"
                and row.get("identity_source") == "sealed_image"):
                return True
        except (ValueError, TypeError, AttributeError):
            continue
    return False


def candidate_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Public report is not an arbitrary JSON passthrough from an artifact."""
    result = {key: value[key] for key in (
        "code_sha", "source_fingerprint", "prepared_archive_sha256", "ci_run_id", "ci_attempt",
        "publication_code_sha",
    )}
    if (not SHA.fullmatch(result["code_sha"]) or not SHA.fullmatch(result["publication_code_sha"])
        or not HEX64.fullmatch(result["source_fingerprint"])
        or not HEX64.fullmatch(result["prepared_archive_sha256"])
        or type(result["ci_run_id"]) is not int or type(result["ci_attempt"]) is not int
        or result["ci_run_id"] <= 0 or result["ci_attempt"] <= 0):
        raise ValueError("eval_deploy_invalid_candidate_metadata")
    result["ci_url"] = f"https://github.com/{REPO}/actions/runs/{result['ci_run_id']}"
    return result


def publish(directory: Path, env: dict[str, str], railway: Railway,
            report: dict[str, Any], *, wait_seconds: float = 900,
            check_only: bool = False) -> dict[str, Any]:
    metadata = candidate_metadata(json.loads(
        (directory / "candidate.json").read_text(encoding="utf-8"),
    ))
    sha, fingerprint = metadata["code_sha"], metadata["source_fingerprint"]
    validate_dispatch(sha, env)
    if sha != env.get("CANDIDATE_SHA") or metadata["publication_code_sha"] != env.get("GITHUB_SHA"):
        raise ValueError("eval_deploy_invalid_fingerprint")
    context = directory / "context"
    if context.is_symlink() or not directory.is_absolute():
        raise ValueError("eval_deploy_invalid_context_path")
    if any(path.is_symlink() for path in context.rglob("*")):
        raise ValueError("eval_deploy_context_symlink")
    for path in context.rglob("*"):
        if path.is_file() and path.relative_to(context).as_posix() not in {
            "Dockerfile", ".dockerignore",
        } and not _include(path.relative_to(context).as_posix()):
            raise ValueError("eval_deploy_context_unexpected_file")
    if (source_fingerprint(context) != fingerprint
        or (context / "Dockerfile").read_bytes() != (context / "evals/Dockerfile").read_bytes()
        or (context / ".dockerignore").read_bytes() != (
            context / "evals/Dockerfile.dockerignore"
        ).read_bytes()
        or (context / "railway.json").exists() or (context / ".git").exists()):
        raise ValueError("eval_deploy_context_changed")
    if railway.call(["--version"]).strip() != "railway " + CLI_VERSION:
        raise ValueError("eval_deploy_cli_version_mismatch")
    report["phase"] = "preflight"
    other, node = inventory(railway.status())
    report.update(metadata, service_id=SERVICE, preflight_verified=True,
                  replica_evidence=single_replica_evidence(node))
    if check_only:
        report.update(status="preflight_verified_no_upload", inference_started=False)
        return report
    report.update(metadata, status="publication_started_no_automatic_retry", service_id=SERVICE)
    report["phase"] = "metadata_variables"
    railway.call(["variable", "set", *SERVICE_TARGET, "--skip-deploys",
                  "ANCORA_EVAL_BUILD_SHA=" + sha, "ANCORA_EVAL_BUILD_SOURCE=" + fingerprint,
                  "RAILWAY_DOCKERFILE_PATH=Dockerfile"])
    report["status"] = "upload_attempted_outcome_unknown"
    report["phase"] = "upload"
    uploaded = json.loads(railway.call([
        "up", str(context), "--path-as-root", *SERVICE_TARGET, "--detach", "--json",
        "--message", "manual-eval:" + sha,
    ], cwd=context))
    deployment_id = uploaded["deploymentId"]
    if not UUID.fullmatch(deployment_id):
        raise ValueError("eval_deploy_missing_deployment_id")
    report.update(deployment_id=deployment_id, status="uploaded_not_verified")
    print(json.dumps({"deployment_id": deployment_id, "status": "uploaded_not_verified"}),
          flush=True)
    started = time.monotonic()
    report["phase"] = "deployment_verification"
    while time.monotonic() - started < wait_seconds:
        deployments = json.loads(railway.call([
            "deployment", "list", *SERVICE_TARGET, "--json", "--limit", "20",
        ]))
        exact = next((d for d in deployments if d["id"] == deployment_id), None)
        if exact and exact["status"] in {"FAILED", "CRASHED", "REMOVED", "SKIPPED"}:
            raise ValueError("eval_deploy_failed_no_automatic_retry")
        if exact and exact["status"] == "SUCCESS":
            current_other, node = inventory(railway.status())
            if current_other != other:
                raise ValueError("eval_deploy_other_services_changed_during_publication")
            instances = (node.get("latestDeployment") or {}).get("instances", [])
            if (node.get("latestDeployment") or {}).get("id") != deployment_id:
                raise ValueError("eval_deploy_superseded")
            logs = railway.call(["logs", deployment_id, *SERVICE_TARGET, "--json", "--lines", "50"])
            if (any(instance.get("status") == "RUNNING" for instance in instances)
                and idle_log(logs, sha, fingerprint)):
                report.update(status="deployed_idle_verified", other_services_unchanged=True,
                              volume_preserved=True, inference_started=False)
                return report
        time.sleep(10)
    raise TimeoutError("eval_deploy_timeout_do_not_retry_blindly")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "check-cli", "publish"])
    parser.add_argument("--sha")
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args(argv)
    if args.command != "check-cli" and args.directory is None:
        parser.error("--directory is required for prepare/publish")
    report: dict[str, Any] = {"status": "blocked", "inference_started": False}
    try:
        if args.command == "check-cli":
            validate_dispatch(os.environ.get("CANDIDATE_SHA", ""), dict(os.environ))
            if Railway(None).call(["--version"]).strip() != "railway " + CLI_VERSION:
                raise ValueError("eval_deploy_cli_version_mismatch")
            report.update(status="cli_verified_without_token", cli_version=CLI_VERSION)
        elif args.command == "prepare":
            report = prepare(ROOT, args.sha or "", args.directory, dict(os.environ))
        else:
            check_only = os.environ.get("EVAL_DEPLOY_CHECK_ONLY", "false")
            if check_only not in {"true", "false"}:
                raise ValueError("eval_deploy_invalid_check_only_flag")
            report = publish(args.directory, dict(os.environ),
                             Railway(os.environ.get("RAILWAY_TOKEN", "")), report,
                             check_only=check_only == "true")
        print(json.dumps(report, ensure_ascii=True))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        report["status"] = "blocked_or_unverified_no_automatic_retry"
        reason = str(error) if isinstance(error, ValueError) else ""
        if re.fullmatch(r"eval_deploy_[a-z_]+", reason):
            report["reason"] = reason
        if isinstance(error, RailwayCommandError):
            report.update(phase=error.phase, command_exit_code=error.exit_code)
        print(json.dumps(report, ensure_ascii=True))
        return 1
    finally:
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with Path(summary).open("a", encoding="utf-8") as stream:
                stream.write("### Evaluador — " + report["status"] + "\n\n```json\n"
                             + json.dumps(report, ensure_ascii=True, indent=2) + "\n```\n")


if __name__ == "__main__":
    raise SystemExit(main())
