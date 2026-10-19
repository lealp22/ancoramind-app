"""Private encrypted synthetic eval evidence, independent from business/telemetry DB.

Append-only files retain evidence, criterion revisions and curated promotions.
One local volume, exclusive process lock; not a distributed or signed ledger.
Metadata and tombstones survive explicit retention purge to prohibit replay.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from src.agent.eval_diagnostics import safe_error_class, safe_terminal_diagnostic

MAX_BYTES = 2_000_000
LABELS = {"pass", "fail", "not_evaluated"}
_SECRET = re.compile(r"sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9_.-]{8,}|"
                     r"postgres(?:ql)?(?:\+asyncpg)?://[^\s\"]+", re.IGNORECASE)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class EvalEvidenceStore:
    """Explicit key and path; never loads ambient .env or credentials itself."""

    def __init__(self, root: Path, key: str):
        if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError("eval_evidence_absolute_private_directory_required")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root = root
        self._cipher = Fernet(key.encode("ascii"))
        self._secret_digest = hashlib.sha256(key.encode()).digest()

    def _run(self, run_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("eval_evidence_invalid_run")
        path = self.root / run_id
        if path.is_symlink():
            raise ValueError("eval_evidence_symlink_forbidden")
        return path

    @contextmanager
    def _lock(self, folder: Path) -> Iterator[None]:
        lock = folder / ".lock"
        if lock.is_symlink():
            raise ValueError("eval_evidence_symlink_forbidden")
        deadline = time.monotonic() + 2
        while True:
            try:
                fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ValueError("eval_evidence_locked_requires_inspection") from None
                time.sleep(0.02)
        os.close(fd)
        try:
            yield
        finally:
            lock.unlink()

    def _write(self, path: Path, value: object) -> None:
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        if (len(raw) > MAX_BYTES or any(p.is_symlink() for p in (path, *path.parents))
            or _SECRET.search(raw.decode())):
            raise ValueError("eval_evidence_invalid_size_or_path")
        # Never retain encryption key bytes; scan potential Fernet-shaped values by hash.
        for candidate in re.findall(rb"[A-Za-z0-9_-]{43}=", raw):
            if hashlib.sha256(candidate).digest() == self._secret_digest:
                raise ValueError("eval_evidence_secret_forbidden")
        encrypted = self._cipher.encrypt(raw)
        temporary = path.with_name(".pending-" + uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            # Publish fully written ciphertext atomically, never overwrite prior event.
            os.link(temporary, path)
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    def _read(self, path: Path) -> dict[str, Any]:
        if (any(p.is_symlink() for p in (path, *path.parents))
            or path.stat().st_size > MAX_BYTES * 2):
            raise ValueError("eval_evidence_invalid_size_or_path")
        try:
            value = json.loads(self._cipher.decrypt(path.read_bytes()))
        except (InvalidToken, ValueError, TypeError):
            raise ValueError("eval_evidence_corrupted_or_wrong_key") from None
        if not isinstance(value, dict):
            raise ValueError("eval_evidence_corrupted")
        return value

    def create(self, identity: dict[str, str], plan: dict[str, Any],
               cases: list[dict[str, Any]], snapshot: dict[str, Any], *,
               synthetic_approved: bool) -> str:
        if not synthetic_approved or not cases or identity.get("worktree") != "clean":
            raise ValueError("eval_evidence_synthetic_approval_required")
        run_id = uuid4().hex
        # Deterministic campaign identity; run UUID never grants an inference replay.
        key = digest({"identity": identity, "plan": plan})
        marker = self.root / (key + ".reserved")
        with self._lock(self.root):
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(run_id)
                stream.flush()
                os.fsync(stream.fileno())
            folder = self._run(run_id)
            folder.mkdir(mode=0o700)
            self._write(folder / "manifest.enc", {
                "version": 1, "run_id": run_id, "created_at": datetime.now(UTC).isoformat(),
                "identity": identity, "plan": plan, "cases": cases, "snapshot": snapshot,
                "synthetic_approved": True, "rubric_fingerprint": digest(cases),
                "retention_days": 7,
            })
            self._head(folder, 0, "")
        return run_id

    def manifest(self, run_id: str, *, allow_expired: bool = False) -> dict[str, Any]:
        folder = self._run(run_id)
        if (folder / "purged").exists():
            raise ValueError("eval_evidence_purged")
        result = self._read(folder / "manifest.enc")
        expiry = datetime.fromisoformat(result["created_at"]) + timedelta(days=7)
        if not allow_expired and datetime.now(UTC) >= expiry:
            raise ValueError("eval_evidence_retention_expired")
        return result

    def _paths(self, run_id: str) -> list[Path]:
        folder = self._run(run_id)
        paths = sorted(folder.glob("event-*.enc"))
        # A durable head makes removal of even the final event detectable.
        head = folder / "head.enc"
        if head.exists():
            expected = self._read(head)
            if len(paths) != expected["count"]:
                raise ValueError("eval_evidence_sequence_corrupted")
            if paths and hashlib.sha256(paths[-1].read_bytes()).hexdigest() != expected["last"]:
                raise ValueError("eval_evidence_chain_corrupted")
        elif paths:
            raise ValueError("eval_evidence_missing_head")
        return paths

    def _head(self, folder: Path, count: int, last: str) -> None:
        # Only mutable artifact is the encrypted tail checkpoint, atomically replaced.
        temporary = folder / (".head-" + uuid4().hex)
        self._write(temporary, {"count": count, "last": last})
        if (folder / "head.enc").is_symlink():
            raise ValueError("eval_evidence_symlink_forbidden")
        os.replace(temporary, folder / "head.enc")

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock(self._run(run_id)):
            return self._events(run_id)

    def _events(self, run_id: str) -> list[dict[str, Any]]:
        self.manifest(run_id)
        result = []
        previous = ""
        paths = self._paths(run_id)
        for index, path in enumerate(paths):
            if path.name != f"event-{index:06d}.enc":
                raise ValueError("eval_evidence_sequence_corrupted")
            event = self._read(path)
            if event.get("previous") != previous or event.get("sequence") != index:
                raise ValueError("eval_evidence_chain_corrupted")
            previous = hashlib.sha256(path.read_bytes()).hexdigest()
            result.append(event)
        return result

    def append(self, run_id: str, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        folder = self._run(run_id)
        with self._lock(folder):
            events = self._events(run_id)
            if kind == "observation" and any(e["kind"] == kind and
                                             e["data"]["case_id"] == data["case_id"]
                                             for e in events):
                raise ValueError("eval_evidence_already_captured")
            if kind == "worker_started" and any(e["kind"] == kind for e in events):
                raise ValueError("eval_worker_already_consumed_no_restart")
            if kind == "review":
                prior = next((e for e in reversed(events) if e["kind"] == kind and
                              e["data"]["case_id"] == data["case_id"] and
                              e["data"]["index"] == data["index"]), None)
                data = {**data, "replaces": prior["sequence"] if prior else None}
            if kind == "review_decision" and any(e["kind"] == kind and
                                                 e["data"]["case_id"] == data["case_id"]
                                                 for e in events):
                raise ValueError("eval_review_decision_already_consumed")
            previous = hashlib.sha256((folder / f"event-{len(events)-1:06d}.enc").read_bytes()
                                      ).hexdigest() if events else ""
            event = {"sequence": len(events), "previous": previous,
                     "at": datetime.now(UTC).isoformat(), "kind": kind, "data": data}
            self._write(folder / f"event-{len(events):06d}.enc", event)
            self._head(folder, len(events) + 1, hashlib.sha256(
                (folder / f"event-{len(events):06d}.enc").read_bytes(),
            ).hexdigest())
            return event

    def capture(self, run_id: str, case_id: str, evidence: dict[str, Any]) -> None:
        if not any(case["id"] == case_id for case in self.manifest(run_id)["cases"]):
            raise ValueError("eval_evidence_unknown_case")
        if self.observation(run_id, case_id) is not None:
            raise ValueError("eval_evidence_already_captured")
        self.append(run_id, "observation", {"case_id": case_id, **evidence})

    def observation(self, run_id: str, case_id: str) -> dict[str, Any] | None:
        return next((e["data"] for e in self.events(run_id)
                     if e["kind"] == "observation" and e["data"]["case_id"] == case_id), None)

    def labels(self, run_id: str, case_id: str) -> dict[int, dict[str, Any]]:
        return {e["data"]["index"]: {**e["data"], "sequence": e["sequence"]}
                for e in self.events(run_id) if e["kind"] == "review"
                and e["data"]["case_id"] == case_id}

    def review(self, run_id: str, case_id: str, index: int, label: str,
               reviewer: str, comment: str = "") -> None:
        manifest = self.manifest(run_id)
        case = next(c for c in manifest["cases"] if c["id"] == case_id)
        if (label not in LABELS or type(index) is not int or not 0 <= index < len(case["criteria"])
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reviewer) or len(comment) > 1000
            or self.observation(run_id, case_id) is None):
            raise ValueError("eval_review_invalid_or_no_evidence")
        old = self.labels(run_id, case_id).get(index)
        self.append(run_id, "review", {"case_id": case_id, "index": index, "label": label,
                                       "reviewer": reviewer, "comment": comment,
                                       "replaces": old["sequence"] if old else None})

    def status(self, run_id: str) -> dict[str, Any]:
        manifest = self.manifest(run_id)
        events = self.events(run_id)
        checkpoint: dict[str, Any] = next((e["data"] for e in reversed(events)
                                          if e["kind"] == "checkpoint"), {})
        from src.agent.eval_validation_session import session_reason

        results = {item["case_id"]: item for item in checkpoint.get("results", [])
                   if isinstance(item, dict) and isinstance(item.get("case_id"), str)}

        def case_diagnostic(case_id: str) -> dict[str, Any]:
            result = results.get(case_id, {})

            def known_state(value: object) -> str | None:
                return value if isinstance(value, str) and value in {
                    "not_started", "started", "passed", "stopped", "failed", "not_evaluated",
                } else None

            value: dict[str, Any] = {
                "execution_status": known_state(result.get("status")),
                "deterministic_status": known_state(result.get("deterministic_status")),
                "semantic_status": known_state(result.get("semantic_status")),
                "error_class": safe_error_class(result.get("error_class")),
                "terminal_diagnostic": safe_terminal_diagnostic(result.get("terminal_diagnostic")),
            }
            value["session_reason"] = session_reason(result.get("session_reason"))
            for name in ("model_calls", "usage_error_count"):
                count = result.get(name)
                value[name] = count if type(count) is int and count >= 0 else None
            return value

        if events and events[-1]["kind"] == "worker_failed":
            checkpoint = {**checkpoint, "status": "uncertain_do_not_restart"}
        worker = next((e["data"] for e in events if e["kind"] == "worker_started"), None)
        # os.kill(pid, 0) is a probe on POSIX, but can terminate a Windows process.
        if os.name != "nt" and worker and checkpoint.get("status") not in {"passed", "stopped"}:
            try:
                os.kill(worker["pid"], 0)
            except ProcessLookupError:
                checkpoint = {**checkpoint, "status": "uncertain_do_not_restart"}
            except PermissionError:
                pass
        return {
            "run_id": run_id, "execution_status": checkpoint.get("status", "not_started"),
            "inference_started": checkpoint.get("inference_started", False),
            "recorded_model_calls": checkpoint.get("recorded_model_calls", 0),
            "error_class": safe_error_class(checkpoint.get("error_class")),
            "session_reason": session_reason(checkpoint.get("session_reason")),
            "cases": [{
                "case_id": c["id"], **case_diagnostic(c["id"]),
                "evidence_available": self.observation(run_id, c["id"]) is not None,
                "criteria": [{"index": i, "label": label["label"]}
                             for i, label in self.labels(run_id, c["id"]).items()],
            } for c in manifest["cases"]],
        }

    def promote(self, run_id: str, case_id: str, *, dataset: str, reviewer: str,
                sanitized_approved: bool, split: str) -> str:
        if (not sanitized_approved or dataset not in {"agent", "judge"}
            or split not in {"development", "validation"}
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", reviewer)):
            raise ValueError("eval_golden_explicit_curation_required")
        manifest = self.manifest(run_id)
        case = next(c for c in manifest["cases"] if c["id"] == case_id)
        observation = self.observation(run_id, case_id)
        labels = self.labels(run_id, case_id)
        if observation is None or observation.get("reply") is None or set(labels) != set(
            range(len(case["criteria"]))
        ) or any(
            label["label"] == "not_evaluated" for label in labels.values()
        ):
            raise ValueError("eval_golden_requires_complete_human_review")
        # Content dedupe crosses run IDs and validation/development splits.
        content = {"case": case} if dataset == "agent" else {
            "case": case, "reply": observation["reply"],
            "proposals": observation["proposals"], "tool_trace": observation["tool_trace"],
            "delivered_text": observation["delivered_text"],
            "labels": [labels[i]["label"] for i in range(len(case["criteria"]))],
        }
        key = digest({"dataset": dataset, "content": content})
        sample_key = digest({"dataset": dataset, "case": case,
                             "reply": observation["reply"] if dataset == "judge" else None})
        golden = self.root / "golden"
        golden.mkdir(exist_ok=True, mode=0o700)
        if golden.is_symlink():
            raise ValueError("eval_evidence_symlink_forbidden")
        with self._lock(golden):
            split_path = golden / (sample_key + ".split.enc")
            if split_path.exists():
                if self._read(split_path)["split"] != split:
                    raise ValueError("eval_golden_train_validation_overlap")
            else:
                self._write(split_path, {"split": split})
            self._write(golden / (key + ".enc"), {
                "schema_version": 1, "dataset": dataset, "split": split, "content": content,
                "label_source": "human_reviewed", "reviewer": reviewer,
                "promoted_at": datetime.now(UTC).isoformat(), "run_id": run_id,
                "identity": manifest["identity"], "plan": manifest["plan"],
                "rubric_fingerprint": manifest["rubric_fingerprint"], "reviews": labels,
            })
        self.append(run_id, "promotion", {"dataset": dataset, "split": split, "version": key})
        return key

    def runs(self) -> list[dict[str, Any]]:
        """Discover recoverable run IDs without reading content into stdout/logs."""
        result = []
        for folder in sorted(self.root.iterdir()):
            if not re.fullmatch(r"[a-f0-9]{32}", folder.name) or not folder.is_dir():
                continue
            if (folder / "purged").exists():
                result.append({"run_id": folder.name, "execution_status": "content_purged"})
                continue
            try:
                result.append(self.status(folder.name))
            except ValueError:
                result.append({"run_id": folder.name, "execution_status": "unavailable"})
        return result

    def export(self, version: str, output: Path, *, sanitized_approved: bool) -> None:
        if (not sanitized_approved or not re.fullmatch(r"[a-f0-9]{64}", version)
            or not output.is_absolute() or any(p.is_symlink() for p in (output, *output.parents))):
            raise ValueError("eval_golden_export_approval_required")
        value = self._read(self.root / "golden" / (version + ".enc"))
        content = value["content"]
        case = content["case"]
        if value["dataset"] == "judge":
            fixture = {
                "schema_version": 1, "rubric_version": value["rubric_fingerprint"],
                "label_source": "human_reviewed", "examples": [{
                    "id": case["id"] + "." + version[:12], "case_id": case["id"],
                    "reply": content["reply"],
                    "criterion_indices": list(range(len(case["criteria"]))),
                    "labels": content["labels"],
                }],
            }
        else:
            fixture = {"schema_version": 1, "category": case["category"], "cases": [{
                "id": case["id"], "description": "Human-curated synthetic regression case",
                "input": case["input"], "context": case["context"], "expected": {
                    "outcome": case["expected_outcome"], "required_tool": case["required_tool"],
                    "forbidden_tools": case["forbidden_tools"],
                    "requires_user_confirmation": case["requires_user_confirmation"],
                    "response_criteria": case["criteria"],
                }, "tags": ["human_curated"],
            }]}
        value["fixture"] = fixture
        if value["dataset"] == "judge":
            value["judge_evidence_contract"] = {
                "requires_case_context_proposals_trace_and_delivered_text": True,
                "current_reply_only_judge_port_sufficient": False,
            }
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if _SECRET.search(raw):
            raise ValueError("eval_golden_secret_forbidden")
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def purge(self, run_id: str) -> None:
        manifest = self.manifest(run_id, allow_expired=True)
        if datetime.now(UTC) < datetime.fromisoformat(manifest["created_at"]) + timedelta(days=7):
            raise ValueError("eval_evidence_retention_not_expired")
        folder = self._run(run_id)
        with self._lock(folder):
            with (folder / "purged").open("x", encoding="ascii") as stream:
                stream.write(datetime.now(UTC).isoformat())
                stream.flush()
                os.fsync(stream.fileno())
            paths = [*folder.glob("*.enc"), *folder.glob(".pending-*"), *folder.glob(".head-*")]
            for path in paths:
                if path.is_symlink():
                    raise ValueError("eval_evidence_symlink_forbidden")
                path.unlink()
