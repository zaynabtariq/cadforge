"""Auditable parameterized repair commands; no executable retrieved code.

Only development evidence may enter the library. A candidate is not reusable
until independent regression evidence passes. IDs hash immutable content.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ParameterCommand:
    parameter: str
    operation: str
    value: float
    source_parameter: str | None = None
    factor: float = 1.0

    def apply(self, parameters: Mapping[str, float]) -> dict[str, float]:
        result = dict(parameters)
        if self.operation not in {"at_least", "at_most", "set", "add"}:
            raise ValueError(f"unsupported operation: {self.operation}")
        target = self.value
        if self.source_parameter is not None:
            target += float(parameters[self.source_parameter]) * self.factor
        if not math.isfinite(target):
            raise ValueError("command target must be finite")
        if self.operation == "set":
            result[self.parameter] = target
        else:
            current = float(parameters[self.parameter])
            result[self.parameter] = {"at_least": max, "at_most": min,
                                      "add": lambda a, b: a + b}[self.operation](current, target)
        if not math.isfinite(result[self.parameter]):
            raise ValueError("command result must be finite")
        return result


@dataclass(frozen=True)
class Evidence:
    case_id: str
    split: str
    passed: bool
    failure_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    commands: tuple[ParameterCommand, ...]
    evidence: tuple[Evidence, ...]
    parent_ids: tuple[str, ...] = ()
    promoted: bool = False
    regression_evidence: tuple[Evidence, ...] = ()


class SkillLibrary:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    @property
    def skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())

    @staticmethod
    def _development(evidence: tuple[Evidence, ...]) -> None:
        if not evidence or any(e.split != "development" for e in evidence):
            raise ValueError("only nonempty development evidence is allowed")

    def propose(self, name: str, commands, evidence, parent_ids=()) -> Skill:
        commands, evidence, parent_ids = tuple(commands), tuple(evidence), tuple(parent_ids)
        self._development(evidence)
        if not commands and not parent_ids:
            raise ValueError("empty skill")
        if not any(not e.passed and e.failure_codes for e in evidence):
            raise ValueError("discovery must include a diagnosed failure")
        for parent in parent_ids:
            if parent not in self._skills or not self._skills[parent].promoted:
                raise ValueError("parents must be previously promoted immutable versions")
        payload = dict(name=name, commands=[asdict(c) for c in commands],
                       evidence=[asdict(e) for e in evidence], parent_ids=parent_ids)
        identifier = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        skill = Skill(identifier, name, commands, evidence, parent_ids)
        self._skills.setdefault(identifier, skill)
        return self._skills[identifier]

    def promote(self, skill_id: str, regression_evidence) -> Skill:
        regression = tuple(regression_evidence)
        self._development(regression)
        skill = self._skills[skill_id]
        discovery_ids = set()
        pending, visited = [skill_id], set()
        while pending:
            identifier = pending.pop()
            if identifier in visited:
                continue
            visited.add(identifier)
            ancestor = self._skills[identifier]
            discovery_ids.update(e.case_id for e in ancestor.evidence)
            pending.extend(ancestor.parent_ids)
        if any(e.case_id in discovery_ids for e in regression):
            raise ValueError("regression cases must be independent of discovery cases")
        if not all(e.passed and not e.failure_codes for e in regression):
            raise ValueError("all independent regressions must pass")
        if skill.promoted:
            if skill.regression_evidence != regression:
                raise ValueError("promoted evidence is immutable")
            return skill
        promoted = replace(skill, promoted=True, regression_evidence=regression)
        self._skills[skill_id] = promoted
        return promoted

    def compose(self, skill_id: str, parameters: Mapping[str, float]) -> dict[str, float]:
        result = dict(parameters)
        visited, active = set(), set()

        def apply(identifier: str):
            nonlocal result
            if identifier in active:
                raise ValueError("inheritance cycle")
            if identifier in visited:
                return
            skill = self._skills[identifier]
            if not skill.promoted:
                raise ValueError("candidate skills cannot be used for inference")
            active.add(identifier)
            for parent in skill.parent_ids:
                apply(parent)
            for command in skill.commands:
                result = command.apply(result)
            active.remove(identifier)
            visited.add(identifier)

        apply(skill_id)
        return result

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps([asdict(s) for s in self.skills], indent=2) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "SkillLibrary":
        library = cls()
        for row in json.loads(Path(path).read_text()):
            ev = lambda rows: tuple(Evidence(**{**e, "failure_codes": tuple(e["failure_codes"])}) for e in rows)
            skill = library.propose(row["name"], [ParameterCommand(**c) for c in row["commands"]],
                                    ev(row["evidence"]), row["parent_ids"])
            if skill.id != row["id"]:
                raise ValueError("skill content hash mismatch")
            if row["promoted"]:
                library.promote(skill.id, ev(row["regression_evidence"]))
        return library
