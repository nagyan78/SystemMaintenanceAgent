from dataclasses import dataclass
from zlib import crc32

from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.repositories.quality_repo import QualityRepository
from backend.app.repositories.taxonomy_repo import TaxonomyRepository
from backend.app.repositories.version_repo import VersionRepository
from backend.app.schemas.quality import VerificationResult


class VerificationFinding(BaseModel):
    issue_id: int
    detector_version: str
    issue_type: str
    logical_node_id: int | None
    normalized_evidence_key: str
    risk_level: str

    @property
    def fingerprint(self) -> str:
        return "|".join(
            (
                self.detector_version,
                self.issue_type,
                str(self.logical_node_id),
                self.normalized_evidence_key,
            )
        )


@dataclass(frozen=True)
class VerificationComparison:
    resolved: list[str]
    unresolved: list[str]
    introduced: list[str]
    introduced_findings: list[VerificationFinding]


class VerificationProbeService:
    DETECTOR_VERSION = "verify-structure-v1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.taxonomy = TaxonomyRepository(settings)

    def build_symmetric_scope(
        self,
        *,
        base_version_id: int,
        result_version_id: int,
        affected_node_ids: list[int],
    ) -> set[int]:
        before = {
            int(item["category_id"]): item
            for item in self.taxonomy.list_nodes(base_version_id)
        }
        after = {
            int(item["category_id"]): item
            for item in self.taxonomy.list_nodes(result_version_id)
        }
        scope = set(affected_node_ids)
        if not scope:
            for node_id in before.keys() | after.keys():
                if _comparable(before.get(node_id)) != _comparable(after.get(node_id)):
                    scope.add(node_id)
        for node_id in list(scope):
            for node_map in (before, after):
                node = node_map.get(node_id)
                if node and node.get("parent_id") is not None:
                    scope.add(int(node["parent_id"]))
        for node_map in (before, after):
            for node_id, node in node_map.items():
                parent_id = node.get("parent_id")
                if parent_id is not None and int(parent_id) in scope:
                    scope.add(node_id)
            for node_id in before.keys() & after.keys():
                if before[node_id].get("path_names") != after[node_id].get("path_names"):
                    scope.add(node_id)
        return scope

    def scan(self, version_id: int, scope: set[int]) -> list[VerificationFinding]:
        nodes = {
            int(item["category_id"]): item
            for item in self.taxonomy.list_nodes(version_id)
        }
        findings: list[VerificationFinding] = []
        sibling_groups: dict[tuple[int | None, str], list[int]] = {}
        for node_id, node in nodes.items():
            key = (node.get("parent_id"), str(node.get("category_name") or "").strip())
            sibling_groups.setdefault(key, []).append(node_id)
        for node_id in sorted(scope):
            node = nodes.get(node_id)
            if node is None:
                continue
            parent_id = node.get("parent_id")
            if parent_id is not None and int(parent_id) not in nodes:
                findings.append(
                    self._finding(
                        "missing_parent", node_id, f"parent:{parent_id}", "high"
                    )
                )
                continue
            if int(node.get("level") or 0) > 7:
                findings.append(
                    self._finding(
                        "deep_level",
                        node_id,
                        f"level:{int(node['level'])}",
                        "medium",
                    )
                )
            expected_path = _expected_path(node_id, nodes)
            if expected_path and expected_path != str(node.get("path_names") or ""):
                findings.append(
                    self._finding(
                        "path_inconsistent",
                        node_id,
                        f"expected:{expected_path}",
                        "high",
                    )
                )
            sibling_key = (
                node.get("parent_id"),
                str(node.get("category_name") or "").strip(),
            )
            if len(sibling_groups[sibling_key]) > 1:
                findings.append(
                    self._finding(
                        "duplicate_name",
                        node_id,
                        f"parent:{node.get('parent_id')};name:{sibling_key[1].casefold()}",
                        "medium",
                    )
                )
        return findings

    def _finding(
        self,
        issue_type: str,
        node_id: int,
        evidence_key: str,
        risk_level: str,
    ) -> VerificationFinding:
        fingerprint = "|".join(
            (self.DETECTOR_VERSION, issue_type, str(node_id), evidence_key)
        )
        return VerificationFinding(
            issue_id=crc32(fingerprint.encode("utf-8")),
            detector_version=self.DETECTOR_VERSION,
            issue_type=issue_type,
            logical_node_id=node_id,
            normalized_evidence_key=evidence_key,
            risk_level=risk_level,
        )


class VerificationIssueComparator:
    def __init__(self, probe: VerificationProbeService) -> None:
        self.probe = probe

    def compare(
        self,
        base_version_id: int,
        result_version_id: int,
        affected_node_ids: list[int],
    ) -> VerificationComparison:
        scope = self.probe.build_symmetric_scope(
            base_version_id=base_version_id,
            result_version_id=result_version_id,
            affected_node_ids=affected_node_ids,
        )
        before = {
            item.fingerprint: item for item in self.probe.scan(base_version_id, scope)
        }
        after = {
            item.fingerprint: item for item in self.probe.scan(result_version_id, scope)
        }
        resolved = sorted(before.keys() - after.keys())
        unresolved = sorted(before.keys() & after.keys())
        introduced = sorted(after.keys() - before.keys())
        return VerificationComparison(
            resolved=resolved,
            unresolved=unresolved,
            introduced=introduced,
            introduced_findings=[after[key] for key in introduced],
        )


class VerificationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.quality = QualityRepository(settings)
        self.comparator = VerificationIssueComparator(VerificationProbeService(settings))

    def verify(
        self,
        *,
        base_version_id: int,
        result_version_id: int,
        affected_node_ids: list[int],
        evaluation_before_id: int,
        evaluation_after_id: int,
        current_round: int,
        max_rounds: int,
    ) -> VerificationResult:
        before = self.quality.get(evaluation_before_id)
        after = self.quality.get(evaluation_after_id)
        if before is None or after is None:
            raise ValueError("Verification requires before and after evaluations")
        if before.score_version != after.score_version:
            raise ValueError("Verification evaluations use different score versions")
        before_available = {
            key for key, available in before.available_dimensions.items() if available
        }
        after_available = {
            key for key, available in after.available_dimensions.items() if available
        }
        if before_available != after_available:
            raise ValueError("Verification evaluations have different available dimensions")

        comparison = self.comparator.compare(
            base_version_id,
            result_version_id,
            affected_node_ids,
        )
        delta = round(after.total_score - before.total_score, 2)
        high_risk = any(
            item.risk_level == "high" for item in comparison.introduced_findings
        )
        if high_risk:
            status = "failed"
            next_decision = "manual_intervention"
        elif not comparison.unresolved and not comparison.introduced and delta >= 0:
            status = "passed"
            next_decision = "finish"
        elif current_round < max_rounds:
            status = "partially_passed"
            next_decision = "ask_continue"
        else:
            status = "degraded"
            next_decision = "finish"
        VersionRepository(self.settings).update_verification_status(
            result_version_id,
            status,
        )
        return VerificationResult(
            status=status,
            resolved_fingerprints=comparison.resolved,
            unresolved_fingerprints=comparison.unresolved,
            introduced_fingerprints=comparison.introduced,
            quality_delta=delta,
            next_decision=next_decision,
            reason=(
                f"verification={status}; quality_delta={delta}; "
                f"resolved={len(comparison.resolved)}; "
                f"unresolved={len(comparison.unresolved)}; "
                f"introduced={len(comparison.introduced)}"
            ),
        )


def _comparable(node: dict | None) -> tuple | None:
    if node is None:
        return None
    return (
        node.get("category_name"),
        node.get("parent_id"),
        node.get("path_names"),
        node.get("syn_list"),
    )


def _expected_path(node_id: int, nodes: dict[int, dict]) -> str | None:
    names: list[str] = []
    seen: set[int] = set()
    current_id = node_id
    while current_id in nodes and current_id not in seen:
        seen.add(current_id)
        node = nodes[current_id]
        names.append(str(node.get("category_name") or ""))
        if node.get("parent_id") is None:
            return " > ".join(reversed(names))
        current_id = int(node["parent_id"])
    return None
