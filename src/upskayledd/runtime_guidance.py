from __future__ import annotations

from dataclasses import dataclass

from upskayledd.config import AppConfig


@dataclass(slots=True, frozen=True)
class RuntimeAction:
    action_id: str
    category: str
    title: str
    detail: str
    status: str
    priority: int

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "priority": self.priority,
        }


class RuntimeGuidanceBuilder:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def build(
        self,
        *,
        doctor_report: dict[str, object],
        model_pack_payload: dict[str, object],
    ) -> list[RuntimeAction]:
        actions: list[RuntimeAction] = []
        check_rules = self.config.runtime_actions.checks
        for check in doctor_report.get("checks", []):
            if not isinstance(check, dict):
                continue
            status = str(check.get("status", "unknown"))
            if status not in {"missing", "degraded"}:
                continue
            name = str(check.get("name", ""))
            rule = check_rules.get(name)
            if rule is None:
                continue
            detail = rule.missing if status == "missing" else rule.degraded
            actions.append(
                RuntimeAction(
                    action_id=f"check:{name}",
                    category=rule.category,
                    title=rule.title,
                    detail=detail,
                    status=status,
                    priority=rule.priority,
                )
            )

        pack_rules = self.config.runtime_actions.packs
        for pack in model_pack_payload.get("packs", []):
            if not isinstance(pack, dict):
                continue
            if bool(pack.get("installed")):
                continue
            pack_id = str(pack.get("id", ""))
            rule = pack_rules.get(pack_id)
            if rule is None:
                continue
            if rule.only_when_recommended and not bool(pack.get("recommended")):
                continue
            actions.append(
                RuntimeAction(
                    action_id=f"pack:{pack_id}",
                    category=rule.category,
                    title=rule.title,
                    detail=rule.missing,
                    status="missing",
                    priority=rule.priority,
                )
            )

        actions.sort(key=lambda item: (-item.priority, item.title))
        return actions[: self.config.runtime_actions.max_actions]
