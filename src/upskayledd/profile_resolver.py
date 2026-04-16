from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from upskayledd.config import AppConfig, ProfileDefinition
from upskayledd.models import InspectionReport


@dataclass(slots=True, frozen=True)
class ResolvedProfile:
    profile: ProfileDefinition
    warnings: tuple[str, ...]


class ProfileResolver:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def resolve_report(self, report: InspectionReport) -> ResolvedProfile:
        if report.manual_review_required:
            return ResolvedProfile(
                profile=self.config.profile_by_id("safe_review_required"),
                warnings=("Low confidence source detection; risky stages suppressed.",),
            )
        for profile in self.config.profiles:
            if report.detected_source_class in profile.source_classes:
                return ResolvedProfile(profile=profile, warnings=())
        return ResolvedProfile(
            profile=self.config.profile_by_id("safe_review_required"),
            warnings=("No exact profile match found; using safe review profile.",),
        )

    def choose_manifest_profile(self, reports: list[InspectionReport]) -> tuple[ProfileDefinition, dict[str, dict[str, str]], list[str]]:
        resolved = [self.resolve_report(report) for report in reports]
        profile_counts = Counter(item.profile.id for item in resolved)
        selected_profile_id = profile_counts.most_common(1)[0][0]
        selected_profile = self.config.profile_by_id(selected_profile_id)
        per_file_overrides: dict[str, dict[str, str]] = {}
        warnings: list[str] = []
        for report, profile in zip(reports, resolved, strict=True):
            warnings.extend(profile.warnings)
            if profile.profile.id != selected_profile_id:
                per_file_overrides[report.source_path] = {
                    "selected_profile_id": profile.profile.id,
                    "reason": "outlier_source_traits",
                }
        if len(profile_counts) > 1:
            warnings.append("Mixed source traits detected across batch; per-file overrides created for outliers.")
        return selected_profile, per_file_overrides, sorted(set(warnings))
