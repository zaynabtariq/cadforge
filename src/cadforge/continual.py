"""Persistent development-only experimental learning with affine hypotheses.

The execution callback is the trust boundary: it must execute real geometry and
return independently measured requirements/checks. This module never generates
its own positive validation evidence and never reads a benchmark corpus.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable

import numpy as np

from .skills import Evidence, ParameterCommand, Skill, SkillLibrary


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class Context:
    environment: str
    material: str
    tool_versions: dict[str, str]
    validator_version: str
    recipe_version: str

    def validate(self):
        if not all((self.environment, self.material, self.tool_versions,
                    self.validator_version, self.recipe_version)):
            raise ValueError("environment, material, tool and recipe/validator versions are required")
        if any(not k or not v for k, v in self.tool_versions.items()):
            raise ValueError("tool versions must be nonempty")


@dataclass(frozen=True)
class Case:
    case_id: str
    task_id: str
    parameters: dict[str, float]
    history_digest: str
    split: str = "development"
    corpus: str = "continual-development"

    def validate(self):
        if self.split != "development" or self.corpus != "continual-development":
            raise ValueError("only fresh continual-development data is permitted; no hidden or v1 ingestion")
        if not self.case_id or not self.task_id or not re.fullmatch(r"[a-f0-9]{64}", self.history_digest):
            raise ValueError("case/task identity and SHA256 task-history digest are required")
        if not self.parameters or any(not math.isfinite(v) for v in self.parameters.values()):
            raise ValueError("finite nonempty parameters required")


@dataclass(frozen=True)
class Measurement:
    passed: bool
    measurements: dict[str, float]
    failure_codes: tuple[str, ...] = ()
    checks: dict[str, bool] = field(default_factory=dict)
    artifact_digests: dict[str, str] = field(default_factory=dict)

    def validate(self):
        if not self.checks or any(type(v) is not bool for v in self.checks.values()):
            raise ValueError("nonempty independently executed boolean checks required")
        if self.passed != all(self.checks.values()):
            raise ValueError("passed must agree with all executed checks")
        if (self.passed and self.failure_codes) or (not self.passed and not self.failure_codes):
            raise ValueError("diagnosed failure codes must agree with passed status")
        if any(not math.isfinite(v) for v in self.measurements.values()):
            raise ValueError("measurements must be finite")
        if any(not re.fullmatch(r"[a-f0-9]{64}", digest) for digest in self.artifact_digests.values()):
            raise ValueError("artifact references require SHA256 digests")


Executor = Callable[[dict[str, float], str], Measurement]


class ContinualLearning:
    """SQLite service; create a separate instance per process/thread.

    Database records are local research artifacts, not a security sandbox.
    Holdout integrity depends on the caller honoring Case provenance.
    """
    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS dependencies (
                child TEXT NOT NULL REFERENCES candidates(id),
                parent TEXT NOT NULL REFERENCES candidates(id), PRIMARY KEY(child,parent));
            CREATE TABLE IF NOT EXISTS validations (
                candidate TEXT NOT NULL REFERENCES candidates(id),
                experiment TEXT NOT NULL REFERENCES experiments(id),
                stage TEXT NOT NULL, PRIMARY KEY(candidate,experiment));
            CREATE TABLE IF NOT EXISTS promotions (
                candidate TEXT PRIMARY KEY REFERENCES candidates(id),
                payload TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS quarantines (
                candidate TEXT PRIMARY KEY REFERENCES candidates(id),
                reason TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
                payload TEXT NOT NULL, created REAL NOT NULL);
            CREATE TRIGGER IF NOT EXISTS immutable_experiments_update BEFORE UPDATE ON experiments
              BEGIN SELECT RAISE(ABORT,'experiments are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_experiments_delete BEFORE DELETE ON experiments
              BEGIN SELECT RAISE(ABORT,'experiments are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_candidates_update BEFORE UPDATE ON candidates
              BEGIN SELECT RAISE(ABORT,'candidate versions are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_candidates_delete BEFORE DELETE ON candidates
              BEGIN SELECT RAISE(ABORT,'candidate versions are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_promotions_update BEFORE UPDATE ON promotions
              BEGIN SELECT RAISE(ABORT,'promotion evidence is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_promotions_delete BEFORE DELETE ON promotions
              BEGIN SELECT RAISE(ABORT,'promotion evidence is immutable'); END;
        """)

    def close(self):
        self.db.close()

    def _event(self, event, **payload):
        self.db.execute("INSERT INTO events(event,payload,created) VALUES(?,?,?)",
                        (event, _json(payload), time.time()))

    def _payload(self, table, identifier):
        if table not in {"experiments", "candidates", "promotions"}:
            raise ValueError("unknown table")
        key = "candidate" if table == "promotions" else "id"
        row = self.db.execute(f"SELECT payload FROM {table} WHERE {key}=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        payload = json.loads(row["payload"])
        if table == "experiments" and _hash(payload) != identifier:
            raise ValueError("experiment content hash mismatch")
        return payload

    def run_experiment(self, case: Case, execute: Executor, *, stage: str,
                       context: Context, parameters: dict[str, float] | None = None) -> str:
        case.validate()
        context.validate()
        if stage not in {"discovery", "counterexample", "transfer", "monitor"}:
            raise ValueError("unknown experimental stage")
        inputs = dict(case.parameters if parameters is None else parameters)
        if any(not math.isfinite(v) for v in inputs.values()):
            raise ValueError("execution inputs must be finite")
        started = time.monotonic()
        try:
            measured = execute(dict(inputs), case.case_id)
            measured.validate()
        except Exception as error:
            measured = Measurement(False, {}, (f"execution:{type(error).__name__}",), {"execution": False})
            error_text = f"{type(error).__name__}: {error}"
        else:
            error_text = None
        payload = {"case": asdict(case), "context": asdict(context), "stage": stage,
                   "inputs": inputs, "measurement": asdict(measured), "error": error_text,
                   "duration_seconds": time.monotonic() - started}
        identifier = _hash(payload)
        with self.db:
            self.db.execute("INSERT INTO experiments VALUES(?,?,?)", (identifier, _json(payload), time.time()))
            self._event("experiment", experiment_id=identifier, stage=stage, passed=measured.passed)
        return identifier

    def _library(self) -> SkillLibrary:
        library = SkillLibrary()
        rows = self.db.execute("SELECT id,payload FROM candidates ORDER BY created,rowid").fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            data = payload["skill"]
            skill = library.propose(data["name"], [ParameterCommand(**c) for c in data["commands"]],
                                    [Evidence(**{**e, "failure_codes": tuple(e["failure_codes"])}) for e in data["evidence"]],
                                    data["parent_ids"])
            if skill.id != row["id"]:
                raise ValueError("stored skill hash mismatch")
            promotion = self.db.execute("SELECT payload FROM promotions WHERE candidate=?", (skill.id,)).fetchone()
            if promotion:
                evidence = json.loads(promotion["payload"])["regression_evidence"]
                library.promote(skill.id, [Evidence(**{**e, "failure_codes": tuple(e["failure_codes"])}) for e in evidence])
        return library

    def _healthy(self, identifier):
        if self.db.execute("SELECT 1 FROM quarantines WHERE candidate=?", (identifier,)).fetchone():
            raise ValueError("candidate/skill is quarantined")

    def propose_affine(self, name: str, target_parameter: str, source_parameters,
                       experiment_ids, *, parent_ids=(), tolerance: float = 1e-6) -> str:
        """Fit target measurement = intercept + sum(factor * input parameter).

        At least n+2 experiments and full-rank independent inputs are required.
        At least one measured discovery failure is required. Linear fit support
        is empirical and bounded to the observed context/ranges, not universal.
        """
        sources, identifiers, parents = tuple(source_parameters), tuple(experiment_ids), tuple(parent_ids)
        if not sources or len(set(sources)) != len(sources) or target_parameter in sources:
            raise ValueError("nonempty unique source parameters distinct from target required")
        if tolerance <= 0 or not math.isfinite(tolerance):
            raise ValueError("positive finite tolerance required")
        if len(set(identifiers)) < len(sources) + 2:
            raise ValueError("need at least source_count + 2 independent experiments")
        rows = [self._payload("experiments", x) for x in identifiers]
        if any(r["stage"] != "discovery" or r["error"] for r in rows):
            raise ValueError("fit requires valid discovery measurements")
        if len({r["case"]["case_id"] for r in rows}) != len(rows):
            raise ValueError("discovery case IDs must be distinct")
        if len({_json(r["context"]) for r in rows}) != 1:
            raise ValueError("discovery environment/material/tool context must be identical")
        matrix = np.array([[1.0] + [r["inputs"][s] for s in sources] for r in rows], dtype=float)
        values = np.array([r["measurement"]["measurements"][target_parameter] for r in rows], dtype=float)
        factors, _, rank, _ = np.linalg.lstsq(matrix, values, rcond=None)
        residual = float(np.max(np.abs(matrix @ factors - values)))
        if rank != len(sources) + 1 or residual > tolerance:
            raise ValueError(f"unsupported affine hypothesis: rank={rank}, max_residual={residual}")
        commands = [ParameterCommand(target_parameter, "set", float(factors[0]))]
        commands.extend(ParameterCommand(target_parameter, "add", 0.0, source, float(factor))
                        for source, factor in zip(sources, factors[1:]))
        for parent in parents:
            self._healthy(parent)
            if self._payload("candidates", parent)["context"] != rows[0]["context"]:
                raise ValueError("inherited context must match discovery context")
        library = self._library()
        evidence = [Evidence(f"{r['case']['case_id']}:{identifier}", "development",
                             r["measurement"]["passed"], tuple(r["measurement"]["failure_codes"]))
                    for identifier, r in zip(identifiers, rows)]
        skill = library.propose(name, commands, evidence, parents)
        payload = {"skill": asdict(skill), "discovery_experiments": identifiers,
                   "context": rows[0]["context"], "target_parameter": target_parameter,
                   "sources": sources, "max_fit_residual": residual, "fit_tolerance": tolerance,
                   "support_ranges": {s: [float(matrix[:, i+1].min()), float(matrix[:, i+1].max())]
                                      for i, s in enumerate(sources)}}
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)",
                            (skill.id, name, _json(payload), time.time()))
            for parent in parents:
                self.db.execute("INSERT OR IGNORE INTO dependencies VALUES(?,?)", (skill.id, parent))
            self._event("hypothesis", candidate_id=skill.id, max_fit_residual=residual)
        return skill.id

    def propose_composition(self, name: str, parent_ids, experiment_ids) -> str:
        """Compose >=2 promoted recipes, then require fresh challenge/transfer.

        This introduces no fitted relationship: its learned content is the
        ordered inherited program and independently validated compatibility.
        """
        parents, identifiers = tuple(parent_ids), tuple(experiment_ids)
        if len(parents) < 2 or len(set(parents)) != len(parents):
            raise ValueError("composition requires at least two distinct parents")
        rows = [self._payload("experiments", x) for x in identifiers]
        if not rows or any(r["stage"] != "discovery" or r["error"] for r in rows):
            raise ValueError("composition needs diagnosed discovery evidence")
        contexts = {_json(r["context"]) for r in rows}
        for parent in parents:
            self._healthy(parent)
            contexts.add(_json(self._payload("candidates", parent)["context"]))
        if len(contexts) != 1:
            raise ValueError("composition context must match every parent")
        evidence = [Evidence(f"{r['case']['case_id']}:{identifier}", "development",
                             r["measurement"]["passed"], tuple(r["measurement"]["failure_codes"]))
                    for identifier, r in zip(identifiers, rows)]
        skill = self._library().propose(name, (), evidence, parents)
        payload = {"skill": asdict(skill), "discovery_experiments": identifiers,
                   "context": rows[0]["context"], "target_parameter": None,
                   "sources": [], "max_fit_residual": None, "fit_tolerance": None,
                   "support_ranges": {}, "method": "inherited_composition"}
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?,?)",
                            (skill.id, name, _json(payload), time.time()))
            for parent in parents:
                self.db.execute("INSERT OR IGNORE INTO dependencies VALUES(?,?)", (skill.id, parent))
            self._event("composition_hypothesis", candidate_id=skill.id, parent_ids=parents)
        return skill.id

    def _candidate_apply(self, identifier, parameters):
        self._healthy(identifier)
        payload = self._payload("candidates", identifier)
        library = self._library()
        result = dict(parameters)
        # Candidate may be tested before promotion; its parents must be promoted.
        # A shared parent in the DAG is executed once through a temporary root.
        for parent in payload["skill"]["parent_ids"]:
            self._healthy(parent)
        skill = next(s for s in library.skills if s.id == identifier)
        from dataclasses import replace
        library._skills[identifier] = replace(skill, promoted=True)
        return library.compose(identifier, result)

    def validate_candidate(self, identifier: str, cases, execute: Executor, *, stage: str,
                           context: Context) -> list[str]:
        if stage not in {"counterexample", "transfer", "monitor"}:
            raise ValueError("validation stage must be counterexample, transfer or monitor")
        self._healthy(identifier)
        payload = self._payload("candidates", identifier)
        context.validate()
        if stage == "transfer" and not self.db.execute(
                "SELECT 1 FROM validations WHERE candidate=? AND stage='counterexample'", (identifier,)).fetchone():
            raise ValueError("counterexample challenge must precede held-out transfer")
        if stage == "monitor" and not self.db.execute(
                "SELECT 1 FROM promotions WHERE candidate=?", (identifier,)).fetchone():
            raise ValueError("monitoring requires a promoted skill")
        if asdict(context) != payload["context"]:
            raise ValueError("context changed: discover and validate a new version")
        ancestors, pending = set(), [identifier]
        while pending:
            item = pending.pop()
            if item in ancestors:
                continue
            ancestors.add(item)
            pending.extend(self._payload("candidates", item)["skill"]["parent_ids"])
        forbidden = set()
        for ancestor in ancestors:
            for experiment in self._payload("candidates", ancestor)["discovery_experiments"]:
                forbidden.add(self._payload("experiments", experiment)["case"]["case_id"])
            if ancestor != identifier:
                parent_validation = self.db.execute("SELECT experiment FROM validations WHERE candidate=?", (ancestor,)).fetchall()
                forbidden.update(self._payload("experiments", r["experiment"])["case"]["case_id"] for r in parent_validation)
        existing = self.db.execute("SELECT experiment FROM validations WHERE candidate=?", (identifier,)).fetchall()
        forbidden.update(self._payload("experiments", r["experiment"])["case"]["case_id"] for r in existing)
        cases = list(cases)
        for case in cases:
            case.validate()
            if case.case_id in forbidden:
                raise ValueError("validation cases must be independent and unused")
            forbidden.add(case.case_id)
        results = []
        for case in cases:
            parameters = self._candidate_apply(identifier, case.parameters)
            experiment = self.run_experiment(case, execute, stage=stage, context=context, parameters=parameters)
            results.append(experiment)
            with self.db:
                self.db.execute("INSERT INTO validations VALUES(?,?,?)", (identifier, experiment, stage))
            if not self._payload("experiments", experiment)["measurement"]["passed"]:
                self.quarantine(identifier, f"{stage} regression: {experiment}")
                break
        return results

    def promote(self, identifier: str) -> Skill:
        self._healthy(identifier)
        payload = self._payload("candidates", identifier)
        existing = self.db.execute("SELECT 1 FROM promotions WHERE candidate=?", (identifier,)).fetchone()
        if existing:
            return next(s for s in self._library().skills if s.id == identifier)
        rows = self.db.execute("SELECT experiment,stage FROM validations WHERE candidate=?", (identifier,)).fetchall()
        if sum(r["stage"] == "counterexample" for r in rows) < 1 or sum(r["stage"] == "transfer" for r in rows) < 2:
            raise ValueError("requires counterexample challenge and at least two held-out development transfers")
        discovery = [self._payload("experiments", x) for x in payload["discovery_experiments"]]
        discovery_tasks = {r["case"]["task_id"] for r in discovery}
        measured = [(r, self._payload("experiments", r["experiment"])) for r in rows]
        if any(r["case"]["task_id"] in discovery_tasks for row, r in measured if row["stage"] == "transfer"):
            raise ValueError("transfer must use tasks independent of discovery")
        evidence = [Evidence(f"{r['case']['case_id']}:{row['experiment']}", "development",
                             r["measurement"]["passed"], tuple(r["measurement"]["failure_codes"]))
                    for row, r in measured]
        library = self._library()
        promoted = library.promote(identifier, evidence)
        with self.db:
            self.db.execute("INSERT INTO promotions VALUES(?,?,?)",
                            (identifier, _json(asdict(promoted)), time.time()))
            self._event("promotion", skill_id=identifier, evidence_count=len(evidence))
        return promoted

    def apply(self, name: str, parameters: dict[str, float], *, context: Context,
              allow_extrapolation: bool = False) -> dict[str, float]:
        return self.apply_with_provenance(name,parameters,context=context,
                                          allow_extrapolation=allow_extrapolation)['parameters']

    def apply_with_provenance(self, name: str, parameters: dict[str, float], *, context: Context,
                              allow_extrapolation: bool = False) -> dict:
        """Resolve dimensions and their exact recipe IDs in one SQLite snapshot.

        Health is evaluated at this read snapshot; geometry must still be checked
        after initialization. Concurrent promotions cannot change the receipt.
        """
        self.db.execute('SAVEPOINT cadforge_apply_snapshot')
        try:
            return self._apply_selection(name,parameters,context=context,
                                         allow_extrapolation=allow_extrapolation)
        finally:
            self.db.execute('RELEASE SAVEPOINT cadforge_apply_snapshot')

    def _apply_selection(self, name, parameters, *, context, allow_extrapolation):
        context.validate()
        rows = self.db.execute("""SELECT c.id,c.payload FROM candidates c JOIN promotions p ON p.candidate=c.id
            LEFT JOIN quarantines q ON q.candidate=c.id WHERE c.name=? AND q.candidate IS NULL
            ORDER BY p.created DESC,p.rowid DESC""", (name,)).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            if payload["context"] != asdict(context):
                continue
            current, visited, active = dict(parameters), set(), set()
            def bounded_apply(identifier):
                nonlocal current
                if identifier in active:
                    raise ValueError("inheritance cycle")
                if identifier in visited:
                    return
                self._healthy(identifier)
                item = self._payload("candidates", identifier)
                if item["context"] != asdict(context):
                    raise ValueError("inherited skill context mismatch")
                active.add(identifier)
                for parent in item["skill"]["parent_ids"]:
                    bounded_apply(parent)
                if not allow_extrapolation:
                    for source, (minimum, maximum) in item["support_ranges"].items():
                        if not minimum - 1e-9 <= current[source] <= maximum + 1e-9:
                            raise ValueError(f"{source} outside observed support; new development experiment required")
                for command in item["skill"]["commands"]:
                    current = ParameterCommand(**command).apply(current)
                active.remove(identifier)
                visited.add(identifier)
            bounded_apply(row["id"])
            return {"parameters":current,"skill_id":row["id"],"dependency_ids":sorted(visited-{row["id"]}),
                    "context":asdict(context),"allow_extrapolation":allow_extrapolation}
        raise KeyError(f"no healthy promoted version of {name!r} in this context")

    def latest_id(self, name: str, *, context: Context) -> str:
        """Resolve the active version for monitoring, using apply's selection rules."""
        context.validate()
        rows = self.db.execute("""SELECT c.id,c.payload FROM candidates c JOIN promotions p ON p.candidate=c.id
            LEFT JOIN quarantines q ON q.candidate=c.id WHERE c.name=? AND q.candidate IS NULL
            ORDER BY p.created DESC,p.rowid DESC""", (name,)).fetchall()
        for row in rows:
            if json.loads(row["payload"])["context"] == asdict(context):
                return row["id"]
        raise KeyError(f"no healthy promoted version of {name!r} in this context")

    def quarantine(self, identifier: str, reason: str) -> list[str]:
        self._payload("candidates", identifier)
        if not reason.strip():
            raise ValueError("quarantine reason required")
        affected, pending = [], [identifier]
        with self.db:
            while pending:
                item = pending.pop()
                if item in affected:
                    continue
                affected.append(item)
                self.db.execute("INSERT OR IGNORE INTO quarantines VALUES(?,?,?)", (item, reason, time.time()))
                pending.extend(r["child"] for r in self.db.execute("SELECT child FROM dependencies WHERE parent=?", (item,)))
            self._event("quarantine", root=identifier, affected=affected, reason=reason)
        return affected

    def audit(self) -> dict:
        return {table: self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("experiments", "candidates", "promotions", "quarantines", "events")}
