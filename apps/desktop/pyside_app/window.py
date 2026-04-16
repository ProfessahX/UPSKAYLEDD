from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from upskayledd.core.paths import resolve_repo_path

from .controller import DesktopController
from .models import CurrentProject, DesktopSessionState
from .ui_config import DashboardCopyConfig, DesktopUiConfig, StageControlConfig, load_ui_config
from .widgets import DropTargetFrame, PayloadViewerDialog, PreviewCompareWidget, QueueBar, StageCardWidget


def _resolve_desktop_asset(ui_config: DesktopUiConfig, asset_name: str) -> Path:
    return resolve_repo_path(getattr(ui_config.assets, asset_name))


def _set_tooltip(widget: QWidget, text: str) -> None:
    if text:
        widget.setToolTip(text)


class IngestPage(QWidget):
    def __init__(self, controller: DesktopController, ui_config: DesktopUiConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.ui_config = ui_config

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(18)

        self.runtime_frame = QFrame()
        self.runtime_frame.setObjectName("panelFrame")
        runtime_layout = QVBoxLayout(self.runtime_frame)
        runtime_layout.setContentsMargins(18, 18, 18, 18)
        runtime_layout.setSpacing(12)
        runtime_title = QLabel(self.ui_config.copy.runtime.title)
        runtime_title.setObjectName("sectionTitle")
        runtime_layout.addWidget(runtime_title)
        self.runtime_headline = QLabel(self.ui_config.copy.runtime.checking.headline)
        self.runtime_headline.setStyleSheet("font-size: 18px; font-weight: 700;")
        runtime_layout.addWidget(self.runtime_headline)
        self.runtime_platform_summary = QLabel(self.ui_config.copy.runtime.platform_empty)
        self.runtime_platform_summary.setWordWrap(True)
        self.runtime_platform_summary.setStyleSheet("color: #9aa8b7; font-size: 12px;")
        runtime_layout.addWidget(self.runtime_platform_summary)
        self.runtime_doctor_summary = QLabel(self.ui_config.copy.runtime.checking.doctor_summary)
        self.runtime_doctor_summary.setWordWrap(True)
        runtime_layout.addWidget(self.runtime_doctor_summary)
        self.runtime_model_summary = QLabel(self.ui_config.copy.runtime.checking.model_summary)
        self.runtime_model_summary.setWordWrap(True)
        runtime_layout.addWidget(self.runtime_model_summary)
        self.runtime_action = QLabel(self.ui_config.copy.runtime.checking.action)
        self.runtime_action.setWordWrap(True)
        self.runtime_action.setStyleSheet("color: #9aa8b7;")
        runtime_layout.addWidget(self.runtime_action)

        insights = QHBoxLayout()
        insights.setSpacing(12)

        checks_frame = QFrame()
        checks_frame.setObjectName("panelFrame")
        checks_layout = QVBoxLayout(checks_frame)
        checks_layout.setContentsMargins(14, 14, 14, 14)
        checks_layout.setSpacing(8)
        checks_title = QLabel(self.ui_config.copy.runtime.focus_title)
        checks_title.setObjectName("sectionTitle")
        checks_layout.addWidget(checks_title)
        self.focus_table = QTableWidget(0, 3)
        self.focus_table.setHorizontalHeaderLabels(["Check", "State", "Detail"])
        self.focus_table.verticalHeader().setVisible(False)
        self.focus_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.focus_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.focus_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.focus_table.setMinimumHeight(150)
        self.focus_table.horizontalHeader().setStretchLastSection(True)
        checks_layout.addWidget(self.focus_table, 1)
        insights.addWidget(checks_frame, 1)

        packs_frame = QFrame()
        packs_frame.setObjectName("panelFrame")
        packs_layout = QVBoxLayout(packs_frame)
        packs_layout.setContentsMargins(14, 14, 14, 14)
        packs_layout.setSpacing(8)
        packs_title = QLabel(self.ui_config.copy.runtime.packs_title)
        packs_title.setObjectName("sectionTitle")
        packs_layout.addWidget(packs_title)
        self.pack_table = QTableWidget(0, 3)
        self.pack_table.setHorizontalHeaderLabels(["Pack", "State", "Tier"])
        self.pack_table.verticalHeader().setVisible(False)
        self.pack_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pack_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.pack_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pack_table.setMinimumHeight(150)
        self.pack_table.horizontalHeader().setStretchLastSection(True)
        packs_layout.addWidget(self.pack_table, 1)
        insights.addWidget(packs_frame, 1)
        runtime_layout.addLayout(insights)

        actions_frame = QFrame()
        actions_frame.setObjectName("panelFrame")
        actions_layout = QVBoxLayout(actions_frame)
        actions_layout.setContentsMargins(14, 14, 14, 14)
        actions_layout.setSpacing(8)
        actions_title = QLabel(self.ui_config.copy.runtime.actions_title)
        actions_title.setObjectName("sectionTitle")
        actions_layout.addWidget(actions_title)
        self.guided_actions_view = QTextEdit()
        self.guided_actions_view.setReadOnly(True)
        self.guided_actions_view.setMinimumHeight(120)
        actions_layout.addWidget(self.guided_actions_view)
        runtime_layout.addWidget(actions_frame)

        locations_frame = QFrame()
        locations_frame.setObjectName("panelFrame")
        locations_layout = QVBoxLayout(locations_frame)
        locations_layout.setContentsMargins(14, 14, 14, 14)
        locations_layout.setSpacing(8)
        locations_title = QLabel(self.ui_config.copy.runtime.locations_title)
        locations_title.setObjectName("sectionTitle")
        locations_layout.addWidget(locations_title)
        self.locations_stack = QVBoxLayout()
        self.locations_stack.setSpacing(8)
        locations_layout.addLayout(self.locations_stack)
        runtime_layout.addWidget(locations_frame)

        setup_actions = QHBoxLayout()
        self.runtime_report_button = QPushButton(self.ui_config.copy.global_text.doctor_button)
        self.runtime_report_button.clicked.connect(self.controller.run_doctor)
        _set_tooltip(self.runtime_report_button, self.ui_config.copy.tooltip("runtime_report_button"))
        setup_actions.addWidget(self.runtime_report_button)
        self.pack_inventory_button = QPushButton(self.ui_config.copy.global_text.model_button)
        self.pack_inventory_button.clicked.connect(self.controller.refresh_model_packs)
        _set_tooltip(self.pack_inventory_button, self.ui_config.copy.tooltip("pack_inventory_button"))
        setup_actions.addWidget(self.pack_inventory_button)
        self.install_recommended_button = QPushButton(self.ui_config.copy.global_text.install_button)
        self.install_recommended_button.clicked.connect(self.controller.install_recommended_models)
        _set_tooltip(self.install_recommended_button, self.ui_config.copy.tooltip("install_recommended_button"))
        setup_actions.addWidget(self.install_recommended_button)
        self.support_bundle_button = QPushButton(self.ui_config.copy.global_text.support_button)
        self.support_bundle_button.clicked.connect(self.controller.export_support_bundle)
        _set_tooltip(self.support_bundle_button, self.ui_config.copy.tooltip("support_bundle_button"))
        setup_actions.addWidget(self.support_bundle_button)
        setup_actions.addStretch(1)
        runtime_layout.addLayout(setup_actions)
        layout.addWidget(self.runtime_frame)

        self.drop_target = DropTargetFrame(
            self.ui_config.copy.ingest.drop_title,
            self.ui_config.copy.ingest.drop_body,
            self.ui_config.copy.tooltip("drop_target"),
        )
        self.drop_target.pathDropped.connect(self._set_target)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(18)
        hero_row.addWidget(self.drop_target, 3)
        brand_frame = self._build_brand_frame()
        if brand_frame is not None:
            hero_row.addWidget(brand_frame, 2)
        layout.addLayout(hero_row, 1)

        recent_frame = QFrame()
        recent_frame.setObjectName("panelFrame")
        recent_layout = QVBoxLayout(recent_frame)
        recent_layout.setContentsMargins(18, 18, 18, 18)
        recent_layout.setSpacing(10)
        recent_title = QLabel(self.ui_config.copy.ingest.recent_title)
        recent_title.setObjectName("sectionTitle")
        recent_layout.addWidget(recent_title)
        self.recent_list = QListWidget()
        self.recent_list.itemDoubleClicked.connect(lambda _item: self._open_selected_recent())
        recent_layout.addWidget(self.recent_list)
        recent_actions = QHBoxLayout()
        self.open_recent_button = QPushButton(self.ui_config.copy.ingest.recent_open_button)
        self.open_recent_button.clicked.connect(self._open_selected_recent)
        _set_tooltip(self.open_recent_button, self.ui_config.copy.tooltip("open_recent_button"))
        recent_actions.addWidget(self.open_recent_button)
        self.prune_recent_button = QPushButton(self.ui_config.copy.ingest.recent_prune_button)
        self.prune_recent_button.clicked.connect(self.controller.prune_recent_targets)
        _set_tooltip(self.prune_recent_button, self.ui_config.copy.tooltip("prune_recent_button"))
        recent_actions.addWidget(self.prune_recent_button)
        recent_actions.addStretch(1)
        recent_layout.addLayout(recent_actions)
        layout.addWidget(recent_frame)

        row = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText(self.ui_config.copy.ingest.target_placeholder)
        _set_tooltip(self.target_input, self.ui_config.copy.tooltip("target_input"))
        row.addWidget(self.target_input, 1)

        browse_button = QPushButton(self.ui_config.copy.ingest.browse_button)
        browse_button.clicked.connect(self._browse)
        _set_tooltip(browse_button, self.ui_config.copy.tooltip("browse_button"))
        row.addWidget(browse_button)

        analyze_button = QPushButton(self.ui_config.copy.ingest.analyze_button)
        analyze_button.clicked.connect(self._analyze)
        analyze_button.setMinimumHeight(42)
        _set_tooltip(analyze_button, self.ui_config.copy.tooltip("analyze_button"))
        row.addWidget(analyze_button)
        layout.addLayout(row)

    def apply_session(self, session: DesktopSessionState) -> None:
        if session.last_target and self.target_input.text().strip() != session.last_target:
            self.target_input.setText(session.last_target)

    def apply_runtime_status(self, payload: dict[str, Any] | None) -> None:
        payload = dict(payload or {})
        self.runtime_headline.setText(payload.get("headline", self.ui_config.copy.runtime.checking.headline))
        self.runtime_platform_summary.setText(payload.get("platform_summary", self.ui_config.copy.runtime.platform_empty))
        self.runtime_doctor_summary.setText(payload.get("doctor_summary", self.ui_config.copy.runtime.checking.doctor_summary))
        self.runtime_model_summary.setText(
            payload.get("model_summary", self.ui_config.copy.runtime.checking.model_summary)
        )
        self.runtime_action.setText(payload.get("action", self.ui_config.copy.runtime.checking.action))
        self._populate_focus_table(list(payload.get("focus_checks", [])))
        self._populate_pack_table(list(payload.get("pack_rows", [])))
        self._populate_guided_actions(list(payload.get("guided_actions", [])))
        self._populate_location_rows(list(payload.get("location_rows", [])))

    def apply_recent_targets(self, rows: list[dict[str, Any]] | None) -> None:
        self.recent_list.clear()
        items = list(rows or [])
        if not items:
            placeholder = QListWidgetItem(self.ui_config.copy.ingest.recent_empty)
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(placeholder)
            self.open_recent_button.setEnabled(False)
            return
        for row in items:
            label = f"{row.get('label', 'Unknown')} · {row.get('kind', 'target').title()}"
            if not row.get("exists", True):
                label += " · Missing"
            details = []
            source_count = row.get("source_count")
            if isinstance(source_count, int) and source_count > 0:
                source_label = "source" if source_count == 1 else "sources"
                details.append(f"{source_count} {source_label}")
            profile_id = str(row.get("recommended_profile_id", "")).strip()
            if profile_id:
                details.append(profile_id)
            manual_review_count = row.get("manual_review_count")
            if isinstance(manual_review_count, int) and manual_review_count > 0:
                details.append(f"{manual_review_count} flagged")
            if details:
                label = f"{label}\n" + " · ".join(details)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, row.get("path", ""))
            item.setToolTip(str(row.get("path", "")))
            self.recent_list.addItem(item)
        self.recent_list.setCurrentRow(0)
        self.open_recent_button.setEnabled(True)

    def _build_brand_frame(self) -> QFrame | None:
        asset_path = _resolve_desktop_asset(self.ui_config, "hero_graphic")
        if not asset_path.exists():
            return None
        pixmap = QPixmap(str(asset_path))
        if pixmap.isNull():
            return None

        frame = QFrame()
        frame.setObjectName("panelFrame")
        frame.setMaximumWidth(self.ui_config.layout.brand_panel_width)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel(self.ui_config.copy.global_text.wordmark)
        title.setStyleSheet("font-size: 26px; font-weight: 800;")
        layout.addWidget(title)

        caption = QLabel(self.ui_config.copy.global_text.tagline)
        caption.setWordWrap(True)
        caption.setStyleSheet("color: #9aa8b7;")
        layout.addWidget(caption)

        graphic = QLabel()
        graphic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        graphic.setPixmap(
            pixmap.scaledToHeight(
                self.ui_config.layout.brand_graphic_height,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(graphic, 1)
        return frame

    def _populate_focus_table(self, rows: list[dict[str, Any]]) -> None:
        display_rows = rows or [
            {
                "name": self.ui_config.copy.runtime.focus_empty,
                "status": "ready",
                "detail": "Nothing missing or degraded in the current runtime check.",
            }
        ]
        self.focus_table.setRowCount(len(display_rows))
        for row_index, row in enumerate(display_rows):
            values = [
                row.get("name", "unknown"),
                str(row.get("status", "unknown")).replace("_", " ").title(),
                row.get("detail", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.focus_table.setItem(row_index, column, item)

    def _populate_pack_table(self, rows: list[dict[str, Any]]) -> None:
        display_rows = rows or [
            {
                "label": self.ui_config.copy.runtime.packs_empty,
                "status": "waiting",
                "recommended": False,
            }
        ]
        self.pack_table.setRowCount(len(display_rows))
        for row_index, row in enumerate(display_rows):
            tier = "Recommended" if row.get("recommended") else "Optional"
            values = [
                row.get("label", "unknown"),
                str(row.get("status", "unknown")).replace("_", " ").title(),
                tier,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                self.pack_table.setItem(row_index, column, item)

    def _populate_guided_actions(self, actions: list[dict[str, Any]]) -> None:
        if not actions:
            self.guided_actions_view.setPlainText(self.ui_config.copy.runtime.actions_empty)
            return
        lines = []
        for index, action in enumerate(actions, start=1):
            lines.append(f"{index}. {action.get('title', 'Next step')}")
            lines.append(f"   {action.get('detail', '')}")
        self.guided_actions_view.setPlainText("\n".join(lines))

    def _populate_location_rows(self, rows: list[dict[str, Any]]) -> None:
        while self.locations_stack.count():
            item = self.locations_stack.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not rows:
            placeholder = QLabel(self.ui_config.copy.runtime.locations_empty)
            placeholder.setWordWrap(True)
            placeholder.setStyleSheet("color: #9aa8b7;")
            self.locations_stack.addWidget(placeholder)
            return

        for row in rows:
            entry = QFrame()
            entry.setObjectName("panelFrame")
            entry_layout = QHBoxLayout(entry)
            entry_layout.setContentsMargins(12, 10, 12, 10)
            entry_layout.setSpacing(12)

            copy_layout = QVBoxLayout()
            copy_layout.setSpacing(2)

            title = QLabel(row.get("label", "Runtime Path"))
            title.setStyleSheet("font-weight: 700;")
            copy_layout.addWidget(title)

            path_label = QLabel(row.get("path", ""))
            path_label.setWordWrap(True)
            path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            path_label.setStyleSheet("color: #9aa8b7;")
            copy_layout.addWidget(path_label)

            detail = QLabel("Ready now" if row.get("exists") else "Created on first use")
            detail.setStyleSheet("color: #5b6670; font-size: 11px;")
            copy_layout.addWidget(detail)

            entry_layout.addLayout(copy_layout, 1)

            button = QPushButton(self.ui_config.copy.runtime.open_location_button)
            button.clicked.connect(
                lambda _checked=False, location_id=str(row.get("location_id", "")): self.controller.open_runtime_location(location_id)
            )
            _set_tooltip(button, self.ui_config.copy.tooltip("open_location_button"))
            entry_layout.addWidget(button)
            self.locations_stack.addWidget(entry)

    def _set_target(self, path: str) -> None:
        self.target_input.setText(path)
        self.controller.ingest_target(path)

    def _browse(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Choose a source file")
        if file_path:
            self.target_input.setText(file_path)
            return
        directory = QFileDialog.getExistingDirectory(self, "Choose a source folder")
        if directory:
            self.target_input.setText(directory)

    def _analyze(self) -> None:
        self.controller.ingest_target(self.target_input.text())

    def _open_selected_recent(self) -> None:
        item = self.recent_list.currentItem()
        if item is None:
            return
        target = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not target:
            return
        self.target_input.setText(target)
        self.controller.open_recent_target(target)


class SummaryPage(QWidget):
    def __init__(self, controller: DesktopController, ui_config: DesktopUiConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.ui_config = ui_config
        self._flagged_source_paths: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        title = QLabel(self.ui_config.copy.summary.title)
        title.setStyleSheet("font-size: 30px; font-weight: 700;")
        layout.addWidget(title)

        intro = QLabel(self.ui_config.copy.summary.intro)
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #9aa8b7;")
        layout.addWidget(intro)

        grid = QHBoxLayout()
        grid.setSpacing(14)
        findings_panel, self.findings_view = self._build_panel("What I Found")
        recommendation_panel, self.recommendation_view = self._build_panel("What I Recommend")
        warning_panel, self.warning_view = self._build_panel("Warnings / Review Flags")
        grid.addWidget(findings_panel, 1)
        grid.addWidget(recommendation_panel, 1)
        grid.addWidget(warning_panel, 1)
        layout.addLayout(grid, 1)

        self.batch_frame = QFrame()
        self.batch_frame.setObjectName("panelFrame")
        batch_layout = QVBoxLayout(self.batch_frame)
        batch_layout.setContentsMargins(18, 18, 18, 18)
        batch_layout.setSpacing(10)

        batch_header = QHBoxLayout()
        batch_title = QLabel(self.ui_config.copy.summary.batch_review_title)
        batch_title.setObjectName("sectionTitle")
        batch_header.addWidget(batch_title)
        batch_header.addStretch(1)
        self.batch_status_label = QLabel(self.ui_config.copy.summary.batch_review_idle)
        self.batch_status_label.setStyleSheet("color: #9aa8b7;")
        batch_header.addWidget(self.batch_status_label)
        batch_layout.addLayout(batch_header)

        self.batch_table = QTableWidget(0, 7)
        self.batch_table.setHorizontalHeaderLabels(
            ["Source", "Class", "Profile", "Confidence", "Flags", "Duration", "Video"]
        )
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.batch_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.batch_table.setSortingEnabled(False)
        self.batch_table.itemSelectionChanged.connect(self._batch_selection_changed)
        self.batch_table.horizontalHeader().setStretchLastSection(True)
        _set_tooltip(self.batch_table, self.ui_config.copy.tooltip("summary_review_selected_button"))
        batch_layout.addWidget(self.batch_table, 1)

        batch_actions = QHBoxLayout()
        self.review_selected_button = QPushButton(self.ui_config.copy.summary.review_selected_button)
        self.review_selected_button.clicked.connect(self._review_selected_source)
        _set_tooltip(self.review_selected_button, self.ui_config.copy.tooltip("summary_review_selected_button"))
        batch_actions.addWidget(self.review_selected_button)
        self.review_flagged_button = QPushButton(self.ui_config.copy.summary.review_flagged_button)
        self.review_flagged_button.clicked.connect(self._review_flagged_source)
        _set_tooltip(self.review_flagged_button, self.ui_config.copy.tooltip("summary_review_flagged_button"))
        batch_actions.addWidget(self.review_flagged_button)
        batch_actions.addStretch(1)
        batch_layout.addLayout(batch_actions)
        self.batch_frame.setVisible(False)
        layout.addWidget(self.batch_frame, 1)

        button_row = QHBoxLayout()
        self.workspace_button = QPushButton(self.ui_config.copy.summary.open_workspace_button)
        self.workspace_button.clicked.connect(self.controller.open_workspace)
        self.workspace_button.setMinimumHeight(42)
        _set_tooltip(self.workspace_button, self.ui_config.copy.tooltip("summary_open_workspace_button"))
        button_row.addWidget(self.workspace_button)

        back_button = QPushButton(self.ui_config.copy.summary.analyze_another_button)
        back_button.clicked.connect(lambda: self.controller.set_page("ingest"))
        _set_tooltip(back_button, self.ui_config.copy.tooltip("summary_analyze_another_button"))
        button_row.addWidget(back_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def _build_panel(self, title: str) -> tuple[QFrame, QTextEdit]:
        frame = QFrame()
        frame.setObjectName("panelFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        layout.addWidget(label)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setMinimumHeight(240)
        layout.addWidget(view, 1)
        return frame, view

    def apply_project(self, payload: dict[str, Any] | None) -> None:
        if payload is None:
            placeholder = self.ui_config.copy.summary.placeholder
            self.findings_view.setPlainText(placeholder)
            self.recommendation_view.setPlainText(placeholder)
            self.warning_view.setPlainText(placeholder)
            self.batch_table.setRowCount(0)
            self.batch_status_label.setText(self.ui_config.copy.summary.batch_review_idle)
            self._flagged_source_paths = []
            self.batch_frame.setVisible(False)
            self._update_batch_action_state()
            return
        project = CurrentProject.from_payload(payload)
        batch_summary = dict(project.batch_summary)
        findings_lines: list[str] = []
        if batch_summary.get("source_count", 0) > 1:
            findings_lines.extend(
                [
                    f"Batch size: {batch_summary.get('source_count', 0)} source files",
                    f"Dominant profile: {batch_summary.get('dominant_profile', project.manifest.selected_profile_id)}",
                    f"Manual review flags: {batch_summary.get('manual_review_count', 0)}",
                    "",
                ]
            )
        for report in project.inspection_reports:
            findings_lines.append(f"[{Path(report['source_path']).name}]")
            findings_lines.extend(f"- {line}" for line in report.get("summary", []))
            findings_lines.append("")

        recommendation_lines = [
            f"Profile: {project.manifest.selected_profile_id}",
            f"Backend: {project.backend_selection.get('backend_id', 'unknown')}",
            f"Output: {project.manifest.output_policy.get('width')}x{project.manifest.output_policy.get('height')} · {project.manifest.output_policy.get('container')}",
            "",
            "Pipeline:",
        ]
        recommendation_lines.extend(
            f"- {stage.label}: {'enabled' if stage.enabled else 'skipped'}"
            for stage in project.manifest.resolved_pipeline_stages
        )
        delivery_guidance = dict(project.delivery_guidance)
        selected_messages = [str(item).strip() for item in delivery_guidance.get("selected_messages", []) if str(item).strip()]
        if selected_messages:
            recommendation_lines.extend(
                [
                    "",
                    f"{self.ui_config.copy.summary.delivery_guidance_label}:",
                ]
            )
            recommendation_lines.extend(f"- {message}" for message in selected_messages)
        alternative_profiles = list(delivery_guidance.get("alternative_profiles", []))
        if alternative_profiles:
            recommendation_lines.extend(
                [
                    "",
                    f"{self.ui_config.copy.summary.alternative_profiles_label}:",
                ]
            )
            for item in alternative_profiles[:3]:
                label = str(item.get("label", item.get("id", "Other lane"))).strip() or "Other lane"
                messages = [str(message).strip() for message in item.get("messages", []) if str(message).strip()]
                if messages:
                    recommendation_lines.append(f"- {label}: {messages[0]}")
                else:
                    recommendation_lines.append(f"- {label}")

        warning_lines = []
        if batch_summary.get("source_count", 0) > 1:
            warning_lines.append(
                "Batch overview: "
                + (
                    "all files align to the same recommended profile."
                    if batch_summary.get("all_match_profile", False)
                    else "this batch contains profile outliers that deserve a closer look."
                )
            )
            warning_lines.append("")
        for report in project.inspection_reports:
            if report.get("warnings"):
                warning_lines.append(f"[{Path(report['source_path']).name}]")
                warning_lines.extend(f"- {warning}" for warning in report["warnings"])
                warning_lines.append("")
        if project.manifest.warnings:
            warning_lines.append("Manifest warnings:")
            warning_lines.extend(f"- {warning}" for warning in project.manifest.warnings)
        if batch_summary.get("flagged_sources"):
            warning_lines.append("")
            warning_lines.append("Flagged sources:")
            warning_lines.extend(
                f"- {Path(item['source_path']).name} (confidence {item['confidence']:.2f})"
                for item in batch_summary["flagged_sources"]
            )
        if not warning_lines:
            warning_lines.append("No review flags from the current recommendation.")

        self.findings_view.setPlainText("\n".join(findings_lines).strip())
        self.recommendation_view.setPlainText("\n".join(recommendation_lines).strip())
        self.warning_view.setPlainText("\n".join(warning_lines).strip())
        self._render_batch_table(project, batch_summary)

    def _render_batch_table(self, project: CurrentProject, batch_summary: dict[str, Any]) -> None:
        rows = list(batch_summary.get("source_rows", []))
        show_batch_table = len(project.source_files) > 1 and bool(rows)
        self.batch_frame.setVisible(show_batch_table)
        self.batch_table.clearSelection()
        self.batch_table.setRowCount(0)
        self._flagged_source_paths = list(batch_summary.get("outlier_sources", []))
        if not show_batch_table:
            self._update_batch_action_state()
            return

        self.batch_status_label.setText(
            self.ui_config.copy.summary.batch_review_aligned
            if batch_summary.get("all_match_profile", False) and not self._flagged_source_paths
            else self.ui_config.copy.summary.batch_review_attention
        )
        self.batch_table.setRowCount(len(rows))
        selected_row = 0
        for row_index, row in enumerate(rows):
            values = [
                row["source_name"],
                row["detected_source_class"],
                row["recommended_profile_id"],
                f"{row['confidence']:.2f}",
                row["flag_summary"],
                self._format_duration(row.get("duration_seconds")),
                row["geometry"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["source_path"])
                item.setToolTip(row["source_path"])
                self.batch_table.setItem(row_index, column, item)
            if row["source_path"] in self._flagged_source_paths:
                selected_row = row_index
        self.batch_table.selectRow(selected_row)
        self._update_batch_action_state()

    def _batch_selection_changed(self) -> None:
        self._update_batch_action_state()

    def _review_selected_source(self) -> None:
        source_path = self._selected_batch_source()
        if not source_path:
            return
        self.controller.open_workspace_for_source(source_path)

    def _review_flagged_source(self) -> None:
        if not self._flagged_source_paths:
            return
        self.controller.open_workspace_for_source(self._flagged_source_paths[0])

    def _selected_batch_source(self) -> str:
        items = self.batch_table.selectedItems()
        if not items:
            return ""
        return str(items[0].data(Qt.ItemDataRole.UserRole) or "")

    def _update_batch_action_state(self) -> None:
        selected = bool(self._selected_batch_source())
        self.review_selected_button.setEnabled(selected)
        self.review_flagged_button.setEnabled(bool(self._flagged_source_paths))

    def _format_duration(self, duration_seconds: float | None) -> str:
        if duration_seconds is None:
            return "unknown"
        if duration_seconds < 60:
            return f"{duration_seconds:.1f}s"
        minutes, seconds = divmod(int(duration_seconds), 60)
        return f"{minutes}m {seconds:02d}s"


class WorkspacePage(QWidget):
    def __init__(self, controller: DesktopController, ui_config: DesktopUiConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.ui_config = ui_config
        self.project: CurrentProject | None = None
        self.session: DesktopSessionState | None = None
        self._rendering = False
        self._stage_cards: dict[str, StageCardWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)

        header = QHBoxLayout()
        self.source_picker = QComboBox()
        self.source_picker.currentTextChanged.connect(self.controller.select_source)
        _set_tooltip(self.source_picker, self.ui_config.copy.tooltip("workspace_source_picker"))
        header.addWidget(QLabel(self.ui_config.copy.workspace.source_label))
        header.addWidget(self.source_picker, 1)

        self.simple_mode_toggle = QCheckBox(self.ui_config.copy.workspace.simple_mode_label)
        self.simple_mode_toggle.toggled.connect(self.controller.set_simple_mode)
        _set_tooltip(self.simple_mode_toggle, self.ui_config.copy.tooltip("workspace_simple_mode"))
        header.addWidget(self.simple_mode_toggle)
        outer.addLayout(header)

        self.source_context_label = QLabel(self.ui_config.copy.workspace.source_context_placeholder)
        self.source_context_label.setWordWrap(True)
        self.source_context_label.setStyleSheet("color: #9aa8b7;")
        outer.addWidget(self.source_context_label)

        self.workspace_split = QHBoxLayout()
        outer.addLayout(self.workspace_split, 1)

        self.stage_rail = QListWidget()
        self.stage_rail.setMaximumWidth(self.ui_config.layout.stage_rail_width)
        self.stage_rail.setSpacing(10)
        self.stage_rail.currentItemChanged.connect(self._stage_selected)
        _set_tooltip(self.stage_rail, self.ui_config.copy.tooltip("workspace_stage_rail"))
        self.workspace_split.addWidget(self.stage_rail)

        detail_frame = QFrame()
        detail_frame.setObjectName("panelFrame")
        detail_frame.setMaximumWidth(self.ui_config.layout.detail_panel_width)
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(12)

        self.stage_title = QLabel("Stage detail")
        self.stage_title.setStyleSheet("font-size: 22px; font-weight: 700;")
        detail_layout.addWidget(self.stage_title)

        self.stage_enabled = QCheckBox("Stage enabled")
        self.stage_enabled.toggled.connect(self._enabled_changed)
        _set_tooltip(self.stage_enabled, self.ui_config.copy.tooltip("workspace_stage_enabled"))
        detail_layout.addWidget(self.stage_enabled)

        self.stage_description = QLabel("Select a stage to inspect its recommendation.")
        self.stage_description.setWordWrap(True)
        self.stage_description.setStyleSheet("color: #9aa8b7;")
        detail_layout.addWidget(self.stage_description)

        self.stage_reason = QLabel("Reason: n/a")
        self.stage_reason.setWordWrap(True)
        self.stage_reason.setStyleSheet("color: #5b6670;")
        detail_layout.addWidget(self.stage_reason)

        self.simple_section_title = QLabel("Recommended Controls")
        self.simple_section_title.setObjectName("sectionTitle")
        detail_layout.addWidget(self.simple_section_title)

        self.simple_form = QFormLayout()
        self.simple_form.setContentsMargins(0, 0, 0, 0)
        detail_layout.addLayout(self.simple_form)

        self.advanced_toggle = QPushButton("Show Advanced")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.toggled.connect(self._advanced_toggled)
        _set_tooltip(self.advanced_toggle, self.ui_config.copy.tooltip("workspace_advanced_toggle"))
        detail_layout.addWidget(self.advanced_toggle)

        self.advanced_container = QWidget()
        advanced_layout = QVBoxLayout(self.advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(10)

        self.advanced_section_title = QLabel("Advanced Controls")
        self.advanced_section_title.setObjectName("sectionTitle")
        advanced_layout.addWidget(self.advanced_section_title)

        self.advanced_form = QFormLayout()
        self.advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addLayout(self.advanced_form)

        self.raw_payload = QTextEdit()
        self.raw_payload.setReadOnly(True)
        self.raw_payload.setMinimumHeight(160)
        advanced_layout.addWidget(self.raw_payload)
        detail_layout.addWidget(self.advanced_container)
        detail_layout.addStretch(1)
        self.workspace_split.addWidget(detail_frame)

        preview_frame = QFrame()
        preview_frame.setObjectName("previewPanel")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        preview_layout.setSpacing(12)

        preview_title = QLabel("Stage Preview")
        preview_title.setStyleSheet("font-size: 22px; font-weight: 700;")
        preview_layout.addWidget(preview_title)

        preview_header = QHBoxLayout()
        self.comparison_mode = QComboBox()
        self.comparison_mode.addItems(list(self.ui_config.preview.comparison_modes))
        _set_tooltip(self.comparison_mode, self.ui_config.copy.tooltip("workspace_comparison_mode"))
        preview_header.addWidget(QLabel("Compare"))
        preview_header.addWidget(self.comparison_mode)

        self.fidelity_mode = QComboBox()
        self.fidelity_mode.addItems(list(self.ui_config.preview.fidelity_modes))
        _set_tooltip(self.fidelity_mode, self.ui_config.copy.tooltip("workspace_fidelity_mode"))
        preview_header.addWidget(QLabel("Fidelity"))
        preview_header.addWidget(self.fidelity_mode)

        self.preview_start = QDoubleSpinBox()
        self.preview_start.setRange(0.0, 36000.0)
        self.preview_start.setSingleStep(1.0)
        _set_tooltip(self.preview_start, self.ui_config.copy.tooltip("workspace_preview_start"))
        preview_header.addWidget(QLabel("Start (s)"))
        preview_header.addWidget(self.preview_start)

        self.preview_duration = QDoubleSpinBox()
        self.preview_duration.setRange(0.5, 30.0)
        self.preview_duration.setValue(self.ui_config.preview.default_sample_duration_seconds)
        self.preview_duration.setSingleStep(0.5)
        _set_tooltip(self.preview_duration, self.ui_config.copy.tooltip("workspace_preview_duration"))
        preview_header.addWidget(QLabel("Duration (s)"))
        preview_header.addWidget(self.preview_duration)
        preview_layout.addLayout(preview_header)

        self.preview_compare = PreviewCompareWidget(tooltips=self.ui_config.copy.tooltips)
        self.comparison_mode.currentTextChanged.connect(self.preview_compare.set_comparison_mode)
        preview_layout.addWidget(self.preview_compare, 1)

        button_row = QHBoxLayout()
        preview_button = QPushButton("Generate Preview")
        preview_button.clicked.connect(self._request_preview)
        _set_tooltip(preview_button, self.ui_config.copy.tooltip("workspace_generate_preview"))
        button_row.addWidget(preview_button)

        queue_button = QPushButton("Queue Project")
        queue_button.clicked.connect(self.controller.queue_current_project)
        _set_tooltip(queue_button, self.ui_config.copy.tooltip("workspace_queue_project"))
        button_row.addWidget(queue_button)

        run_button = QPushButton("Run Project")
        run_button.clicked.connect(lambda: self.controller.run_current_project(execute_degraded=False))
        _set_tooltip(run_button, self.ui_config.copy.tooltip("workspace_run_project"))
        button_row.addWidget(run_button)

        degraded_button = QPushButton("Run Degraded")
        degraded_button.clicked.connect(lambda: self.controller.run_current_project(execute_degraded=True))
        _set_tooltip(degraded_button, self.ui_config.copy.tooltip("workspace_run_degraded"))
        button_row.addWidget(degraded_button)
        button_row.addStretch(1)
        preview_layout.addLayout(button_row)

        self.workspace_split.addWidget(preview_frame, 1)

        self._setting_widgets: dict[str, QWidget] = {}
        self.comparison_mode.currentTextChanged.connect(self.controller.set_comparison_mode)
        self.fidelity_mode.currentTextChanged.connect(self.controller.set_fidelity_mode)
        self.preview_start.valueChanged.connect(lambda value: self.controller.set_preview_window(start_seconds=value))
        self.preview_duration.valueChanged.connect(lambda value: self.controller.set_preview_window(duration_seconds=value))

    def apply_session(self, session: DesktopSessionState) -> None:
        self.session = session
        self._render()

    def apply_project(self, payload: dict[str, Any] | None) -> None:
        self.project = CurrentProject.from_payload(payload) if payload else None
        self._render()

    def apply_preview(self, payload: dict[str, Any] | None) -> None:
        if payload is None:
            self.preview_compare.clear_preview()
            return
        self.preview_compare.set_comparison_mode(self.comparison_mode.currentText())
        self.preview_compare.load_preview(payload, auto_play=self.ui_config.behavior.auto_play_preview)

    def _render(self) -> None:
        self._rendering = True
        try:
            self.simple_mode_toggle.setChecked(self.session.simple_mode if self.session else self.ui_config.behavior.default_simple_mode)
            self.comparison_mode.blockSignals(True)
            self.fidelity_mode.blockSignals(True)
            self.preview_start.blockSignals(True)
            self.preview_duration.blockSignals(True)
            self.comparison_mode.setCurrentText(self.session.comparison_mode if self.session else self.ui_config.preview.default_comparison_mode)
            self.fidelity_mode.setCurrentText(self.session.fidelity_mode if self.session else self.ui_config.preview.default_fidelity_mode)
            self.preview_start.setValue(self.session.preview_start_seconds if self.session else self.ui_config.preview.default_sample_start_seconds)
            self.preview_duration.setValue(self.session.preview_duration_seconds if self.session else self.ui_config.preview.default_sample_duration_seconds)
            self.comparison_mode.blockSignals(False)
            self.fidelity_mode.blockSignals(False)
            self.preview_start.blockSignals(False)
            self.preview_duration.blockSignals(False)
            self.source_picker.blockSignals(True)
            self.source_picker.clear()
            if self.project is not None:
                self.source_picker.addItems(self.project.source_files)
                source = self.session.selected_source or self.project.source_files[0]
                index = max(0, self.source_picker.findText(source))
                self.source_picker.setCurrentIndex(index)
            self.source_picker.blockSignals(False)
            self.source_context_label.setText(self._source_context_text())

            self.stage_rail.blockSignals(True)
            self.stage_rail.clear()
            self._stage_cards.clear()
            if self.project is not None:
                for stage in self.project.manifest.resolved_pipeline_stages:
                    stage_meta = self.ui_config.stage(stage.stage_id)
                    item = QListWidgetItem()
                    item.setData(Qt.ItemDataRole.UserRole, stage.stage_id)
                    self.stage_rail.addItem(item)
                    card = StageCardWidget(
                        title=stage_meta.rail_label if stage_meta else stage.label,
                        status=self._stage_status(stage),
                        summary=self._stage_summary(stage),
                        tooltip=(stage_meta.description if stage_meta else stage.label),
                    )
                    item.setSizeHint(card.sizeHint())
                    self.stage_rail.setItemWidget(item, card)
                    self._stage_cards[stage.stage_id] = card
                selected_stage = self.session.selected_stage if self.session else self.ui_config.preview.default_stage
                for index in range(self.stage_rail.count()):
                    item = self.stage_rail.item(index)
                    if item.data(Qt.ItemDataRole.UserRole) == selected_stage:
                        self.stage_rail.setCurrentRow(index)
                        break
                if self.stage_rail.currentRow() < 0 and self.stage_rail.count():
                    self.stage_rail.setCurrentRow(0)
            self.stage_rail.blockSignals(False)
            self._refresh_stage_selection()
            self._render_stage_detail()
        finally:
            self._rendering = False

    def _render_stage_detail(self) -> None:
        self._clear_form(self.simple_form)
        self._clear_form(self.advanced_form)
        self._setting_widgets.clear()

        if self.project is None:
            self.stage_title.setText("Stage detail")
            self.stage_description.setText("Analyze a source to unlock the workspace.")
            self.stage_reason.setText("Analyze a source to unlock the workspace.")
            self.raw_payload.setPlainText("")
            return

        stage = self.project.stage_by_id(self.session.selected_stage if self.session else "")
        if stage is None:
            return
        stage_meta = self.ui_config.stage(stage.stage_id)

        self.stage_title.setText(stage_meta.rail_label if stage_meta else stage.label)
        self.stage_enabled.setChecked(stage.enabled)
        self.stage_description.setText(stage_meta.description if stage_meta else "Configure the selected pipeline stage.")
        self.stage_reason.setText(f"Status: {self._stage_status(stage)}")

        controls = list(stage_meta.controls) if stage_meta else self._fallback_controls(stage)
        simple_controls = [control for control in controls if control.tier == "simple"]
        advanced_controls = [control for control in controls if control.tier != "simple"]

        self.simple_section_title.setText(stage_meta.simple_section_title if stage_meta else "Recommended Controls")
        self.advanced_section_title.setText(stage_meta.advanced_section_title if stage_meta else "Advanced Controls")
        self._render_controls(self.simple_form, stage, simple_controls, empty_text="No quick controls for this stage.")
        self._render_controls(self.advanced_form, stage, advanced_controls, empty_text="No advanced controls yet. Raw stage payload is available below for inspection.")

        expanded = self.session.stage_expansion_memory.get(stage.stage_id, not self.session.simple_mode) if self.session else False
        self.advanced_toggle.blockSignals(True)
        self.advanced_toggle.setChecked(expanded)
        self.advanced_toggle.setText("Hide Advanced" if expanded else "Show Advanced")
        self.advanced_toggle.blockSignals(False)
        self.advanced_container.setVisible(expanded)
        self.raw_payload.setPlainText(json.dumps(stage.to_dict(), indent=2, sort_keys=True))

    def _stage_selected(self, current: QListWidgetItem | None, _: QListWidgetItem | None) -> None:
        if self._rendering:
            return
        if current is None:
            return
        stage_id = str(current.data(Qt.ItemDataRole.UserRole) or "")
        self.controller.select_stage(stage_id)
        self._refresh_stage_selection()

    def _enabled_changed(self, enabled: bool) -> None:
        if self._rendering or self.project is None:
            return
        stage = self.project.stage_by_id(self.session.selected_stage)
        if stage is not None:
            self.controller.update_stage_enabled(stage.stage_id, enabled)

    def _control_changed(self, stage_id: str, control: StageControlConfig, value: Any) -> None:
        if self._rendering:
            return
        if control.source == "output_policy":
            self.controller.update_output_policy(control.key, value)
        else:
            self.controller.update_stage_setting(stage_id, control.key, value)

    def _advanced_toggled(self, enabled: bool) -> None:
        if self._rendering or self.project is None or self.session is None:
            return
        stage_id = self.session.selected_stage
        self.advanced_toggle.setText("Hide Advanced" if enabled else "Show Advanced")
        self.advanced_container.setVisible(enabled)
        self.controller.set_stage_expanded(stage_id, enabled)

    def _request_preview(self) -> None:
        self.preview_compare.set_comparison_mode(self.comparison_mode.currentText())
        self.controller.request_preview(
            comparison_mode=self.comparison_mode.currentText(),
            fidelity_mode=self.fidelity_mode.currentText(),
            sample_start_seconds=self.preview_start.value(),
            sample_duration_seconds=self.preview_duration.value(),
        )

    def _clear_form(self, layout: QFormLayout) -> None:
        while layout.rowCount():
            layout.removeRow(0)

    def _render_controls(
        self,
        layout: QFormLayout,
        stage,
        controls: list[StageControlConfig],
        *,
        empty_text: str,
    ) -> None:
        if not controls:
            label = QLabel(empty_text)
            label.setWordWrap(True)
            label.setStyleSheet("color: #9aa8b7;")
            layout.addRow("", label)
            return
        for control in controls:
            widget = self._make_control_editor(stage, control)
            if widget is None:
                continue
            widget.setToolTip(control.help)
            layout.addRow(control.label, widget)
            self._setting_widgets[f"{stage.stage_id}:{control.source}:{control.key}"] = widget

    def _make_control_editor(self, stage, control: StageControlConfig) -> QWidget | None:
        value = self._control_value(stage, control)
        if control.widget == "label":
            label = QLabel(str(value))
            label.setWordWrap(True)
            label.setStyleSheet("color: #9aa8b7;")
            return label
        if control.widget == "combo":
            combo = QComboBox()
            options = self._combo_items_for_control(control)
            known_values = [option_value for _, option_value in options]
            if str(value) and str(value) not in known_values:
                options.append((str(value), str(value)))
            for label, option_value in options:
                combo.addItem(label, option_value)
            current_index = next(
                (index for index in range(combo.count()) if str(combo.itemData(index)) == str(value)),
                0,
            )
            combo.setCurrentIndex(current_index)
            combo.currentIndexChanged.connect(
                lambda index: self._control_changed(
                    stage.stage_id,
                    control,
                    combo.itemData(index),
                )
            )
            return combo
        if control.widget == "bool":
            checkbox = QCheckBox()
            checkbox.setChecked(bool(value))
            checkbox.stateChanged.connect(
                lambda _state: self._control_changed(stage.stage_id, control, checkbox.isChecked())
            )
            return checkbox
        if control.widget == "int":
            spin = QSpinBox()
            spin.setRange(int(control.minimum or -8192), int(control.maximum or 8192))
            spin.setSingleStep(int(control.step or 1))
            spin.setValue(int(value or 0))
            spin.valueChanged.connect(lambda changed: self._control_changed(stage.stage_id, control, changed))
            return spin
        if control.widget == "float":
            spin = QDoubleSpinBox()
            spin.setRange(float(control.minimum or -1000.0), float(control.maximum or 1000.0))
            spin.setSingleStep(float(control.step or 0.5))
            spin.setDecimals(3)
            spin.setValue(float(value or 0.0))
            spin.valueChanged.connect(lambda changed: self._control_changed(stage.stage_id, control, changed))
            return spin
        line = QLineEdit(str(value))
        line.editingFinished.connect(lambda: self._control_changed(stage.stage_id, control, line.text()))
        return line

    def _combo_items_for_control(self, control: StageControlConfig) -> list[tuple[str, str]]:
        if control.options:
            return [(option, option) for option in control.options]
        if control.source == "output_policy" and control.key == "encode_profile_id":
            return [
                (profile.label, profile.id)
                for profile in self.controller.service.config.encode.profiles
            ]
        if control.source == "output_policy" and control.key == "container":
            return [
                (container.upper(), container)
                for container in self.controller.service.config.supported_output_containers()
            ]
        return []

    def _control_value(self, stage, control: StageControlConfig) -> Any:
        if self.project is None:
            return ""
        if control.source == "output_policy":
            return self.project.manifest.output_policy.get(control.key, "")
        return stage.settings.get(control.key, "")

    def _fallback_controls(self, stage) -> list[StageControlConfig]:
        controls: list[StageControlConfig] = []
        for key in stage.settings:
            widget = "combo" if key == "mode" else ("label" if key == "notes" else "text")
            options = tuple(sorted(self.controller.service.config.stage_presets.stages.get(stage.stage_id, {}).keys())) if key == "mode" else ()
            tier = "simple" if key in {"mode", "notes"} else "advanced"
            controls.append(
                StageControlConfig(
                    key=key,
                    label=key.replace("_", " ").title(),
                    source="stage",
                    widget=widget,
                    tier=tier,
                    options=options,
                )
            )
        return controls

    def _refresh_stage_selection(self) -> None:
        current = self.session.selected_stage if self.session else ""
        for stage_id, card in self._stage_cards.items():
            card.set_selected(stage_id == current)

    def _stage_status(self, stage) -> str:
        if not stage.enabled:
            return "Skipped"
        if stage.reason == "customized":
            return "Custom"
        if "manual_review" in stage.reason or "suppressed" in stage.reason:
            return "Review"
        return "Default"

    def _source_context_text(self) -> str:
        if self.project is None:
            return self.ui_config.copy.workspace.source_context_placeholder
        batch_summary = dict(self.project.batch_summary)
        rows = list(batch_summary.get("source_rows", []))
        if len(self.project.source_files) <= 1 or not rows:
            return self.ui_config.copy.workspace.source_context_placeholder
        selected_source = self.source_picker.currentText().strip()
        selected_row = next((row for row in rows if row.get("source_path") == selected_source), None)
        if selected_row is None:
            return self.ui_config.copy.workspace.source_context_placeholder
        if selected_row.get("manual_review_required"):
            return self.ui_config.copy.workspace.source_context_manual_review.format(
                source_name=selected_row.get("source_name", "Selected source"),
                confidence=float(selected_row.get("confidence", 0.0)),
            )
        if selected_row.get("profile_outlier") or selected_row.get("warning_count", 0):
            return self.ui_config.copy.workspace.source_context_outlier.format(
                source_name=selected_row.get("source_name", "Selected source"),
                recommended_profile_id=selected_row.get("recommended_profile_id", self.project.manifest.selected_profile_id),
            )
        return self.ui_config.copy.workspace.source_context_aligned.format(
            source_name=selected_row.get("source_name", "Selected source"),
            recommended_profile_id=selected_row.get("recommended_profile_id", self.project.manifest.selected_profile_id),
        )

    def _stage_summary(self, stage) -> str:
        if self.project is None:
            return "No summary"
        stage_meta = self.ui_config.stage(stage.stage_id)
        if stage_meta is None:
            return str(stage.settings.get("mode", stage.reason or "Recommended"))
        values = dict(stage.settings)
        values.update(
            {
                "width": self.project.manifest.output_policy.get("width", ""),
                "height": self.project.manifest.output_policy.get("height", ""),
                "container": self.project.manifest.output_policy.get("container", ""),
                "container_label": str(self.project.manifest.output_policy.get("container", "")).upper(),
                "encode_profile_id": self.project.manifest.output_policy.get("encode_profile_id", ""),
                "encode_profile_label": self._encode_profile_label(),
            }
        )
        try:
            return str(stage_meta.summary_template.format(**values))
        except Exception:  # noqa: BLE001
            return str(stage.settings.get("mode", stage.reason or "Recommended"))

    def _encode_profile_label(self) -> str:
        if self.project is None:
            return ""
        encode_profile_id = str(self.project.manifest.output_policy.get("encode_profile_id", "")).strip()
        if not encode_profile_id:
            return ""
        try:
            return self.controller.service.config.encode_profile_by_id(encode_profile_id).label
        except Exception:  # noqa: BLE001
            return encode_profile_id


def build_run_summary(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return ""
    encode_settings = dict(payload.get("encode_settings", {}))
    actual_backend = dict(payload.get("actual_backend", {}))
    lines = [
        f"Execution mode: {encode_settings.get('execution_mode', 'not run yet')}",
    ]
    backend_used = str(payload.get("actual_backend_used") or actual_backend.get("backend_id") or "").strip()
    if backend_used:
        lines.append(f"Backend: {backend_used}")
    output_files = list(payload.get("output_files", []))
    if output_files:
        lines.append(f"Primary output: {Path(output_files[0]).name}")
        if len(output_files) > 1:
            lines.append(f"Additional outputs: {len(output_files) - 1}")
    input_size = encode_settings.get("input_size_bytes")
    output_size = encode_settings.get("output_size_bytes")
    size_ratio = encode_settings.get("size_ratio")
    if input_size and output_size:
        lines.append(
            "Size: "
            f"{int(output_size):,} bytes out"
            f" vs {int(input_size):,} bytes in"
            + (f" ({float(size_ratio):.2f}x)" if size_ratio not in (None, "") else "")
        )
    media_metrics = dict(encode_settings.get("media_metrics", {}))
    input_metrics = dict(media_metrics.get("input", {}))
    output_metrics = dict(media_metrics.get("output", {}))
    comparison_metrics = dict(media_metrics.get("comparison", {}))
    if input_metrics or output_metrics:
        lines.append("")
        lines.append("Media metrics:")
        if input_metrics:
            lines.extend(_format_media_metrics_block("Input", input_metrics))
        if output_metrics:
            lines.extend(_format_media_metrics_block("Output", output_metrics))
        comparison_lines = _format_media_comparison_lines(comparison_metrics)
        if comparison_lines:
            lines.append("Comparison:")
            lines.extend(comparison_lines)
    stream_outcomes = list(payload.get("stream_outcomes", []))
    if stream_outcomes:
        lines.append("")
        lines.append("Streams:")
        for item in stream_outcomes:
            stream_type = str(item.get("stream_type", "stream")).replace("_", " ")
            action = str(item.get("action", "unknown")).replace("_", " ")
            reason = str(item.get("reason", "")).replace("_", " ")
            lines.append(f"- {stream_type}: {action}" + (f" ({reason})" if reason else ""))
    fallbacks = list(payload.get("fallbacks", []))
    if fallbacks:
        lines.append("")
        lines.append("Fallbacks:")
        lines.extend(f"- {str(item).replace('_', ' ')}" for item in fallbacks)
    warnings = list(payload.get("warnings", []))
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in warnings)
    guidance = list(encode_settings.get("conversion_guidance", []))
    if guidance:
        lines.append("")
        lines.append("Conversion guidance:")
        lines.extend(f"- {item}" for item in guidance)
    return "\n".join(lines)


def build_media_metrics_snapshot(payload: dict[str, Any] | None) -> dict[str, list[Any]]:
    if payload is None:
        return {"rows": [], "guidance": []}
    encode_settings = dict(payload.get("encode_settings", {}))
    media_metrics = dict(encode_settings.get("media_metrics", {}))
    input_metrics = dict(media_metrics.get("input", {}))
    output_metrics = dict(media_metrics.get("output", {}))
    if not input_metrics and not output_metrics:
        return {"rows": [], "guidance": []}

    rows: list[tuple[str, str, str]] = [
        ("Container", _format_container(input_metrics), _format_container(output_metrics)),
        ("File size", _format_size(input_metrics.get("size_bytes")), _format_size(output_metrics.get("size_bytes"))),
        ("Duration", _format_duration(input_metrics.get("duration_seconds")), _format_duration(output_metrics.get("duration_seconds"))),
        ("Video", _format_video_metrics(dict(input_metrics.get("video", {}))), _format_video_metrics(dict(output_metrics.get("video", {})))),
        ("Audio", _format_audio_metrics(dict(input_metrics.get("audio", {}))), _format_audio_metrics(dict(output_metrics.get("audio", {})))),
        ("Subtitles", _format_subtitle_metrics(dict(input_metrics.get("subtitle", {}))), _format_subtitle_metrics(dict(output_metrics.get("subtitle", {})))),
        (
            "Chapters",
            str(int(input_metrics.get("chapter_count", 0) or 0)),
            str(int(output_metrics.get("chapter_count", 0) or 0)),
        ),
    ]
    guidance = [
        str(item).strip()
        for item in encode_settings.get("conversion_guidance", [])
        if str(item).strip()
    ]
    if not guidance:
        comparison = dict(media_metrics.get("comparison", {}))
        guidance = [
            line.removeprefix("- ").strip()
            for line in _format_media_comparison_lines(comparison)
            if line.strip()
        ]
    return {"rows": rows, "guidance": guidance}


def build_media_change_highlights(payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if payload is None:
        return []
    encode_settings = dict(payload.get("encode_settings", {}))
    media_metrics = dict(encode_settings.get("media_metrics", {}))
    input_metrics = dict(media_metrics.get("input", {}))
    output_metrics = dict(media_metrics.get("output", {}))
    comparison = dict(media_metrics.get("comparison", {}))
    input_video = dict(input_metrics.get("video", {}))
    output_video = dict(output_metrics.get("video", {}))
    guidance = [
        str(item).strip()
        for item in encode_settings.get("conversion_guidance", [])
        if str(item).strip()
    ] or [
        str(item).strip()
        for item in comparison.get("guidance", [])
        if str(item).strip()
    ]

    highlights: list[dict[str, str]] = []

    size_ratio = comparison.get("size_ratio")
    if size_ratio not in (None, ""):
        ratio_value = float(size_ratio)
        if ratio_value > 1.05:
            size_tone = "danger"
        elif ratio_value < 0.60:
            size_tone = "warning"
        else:
            size_tone = "success"
        highlights.append(
            {
                "title": "Size",
                "value": _format_ratio_percent(ratio_value),
                "detail": _pick_guidance(
                    guidance,
                    "larger than the source sample",
                    "shrank aggressively",
                    "current delivery settings",
                )
                or f"Output landed at {ratio_value:.2f}x the source sample size.",
                "tone": size_tone,
            }
        )

    input_resolution = _format_resolution(input_video)
    output_resolution = _format_resolution(output_video)
    if input_resolution != "unknown resolution" and output_resolution != "unknown resolution":
        highlights.append(
            {
                "title": "Resolution",
                "value": f"{input_resolution} -> {output_resolution}",
                "detail": (
                    f"Resolution scale is {float(comparison.get('resolution_scale', 0.0) or 0.0):.2f}x."
                    if comparison.get("resolution_scale") not in (None, "")
                    else "Source and output resolution are shown here for quick review."
                ),
                "tone": "info",
            }
        )

    input_fps = input_video.get("avg_frame_rate_fps")
    output_fps = output_video.get("avg_frame_rate_fps")
    if input_fps not in (None, "") and output_fps not in (None, ""):
        input_fps_value = float(input_fps)
        output_fps_value = float(output_fps)
        if abs(input_fps_value - output_fps_value) >= 0.5:
            highlights.append(
                {
                    "title": "Cadence",
                    "value": f"{input_fps_value:.2f} -> {output_fps_value:.2f} fps",
                    "detail": _pick_guidance(guidance, "Frame rate changed")
                    or "Frame rate changed materially between source and output. Review motion before committing a long batch.",
                    "tone": "warning",
                }
            )

    subtitle_stream_delta = int(comparison.get("subtitle_stream_delta", 0) or 0)
    chapter_delta = int(comparison.get("chapter_delta", 0) or 0)
    audio_changed = bool(comparison.get("audio_codec_changed"))
    subtitle_changed = bool(comparison.get("subtitle_codec_changed"))
    if subtitle_stream_delta < 0 or chapter_delta < 0:
        stream_value = "Loss detected"
        stream_detail = "One or more subtitle or chapter streams dropped during delivery. Review the manifest before trusting this lane."
        stream_tone = "danger"
    elif audio_changed or subtitle_changed:
        stream_value = "Delivery changed"
        stream_detail = "Audio or subtitle delivery changed for compatibility or encode reasons. Hover here, then inspect the metrics table if you need the specifics."
        stream_tone = "warning"
    else:
        stream_value = "Preserved"
        stream_detail = "Audio, subtitle, and chapter counts held steady between the source and output sample."
        stream_tone = "success"
    highlights.append(
        {
            "title": "Streams",
            "value": stream_value,
            "detail": stream_detail,
            "tone": stream_tone,
        }
    )

    return highlights[:4]


def _format_media_metrics_block(label: str, metrics: dict[str, Any]) -> list[str]:
    video = dict(metrics.get("video", {}))
    audio = dict(metrics.get("audio", {}))
    subtitle = dict(metrics.get("subtitle", {}))
    return [
        f"{label}: {_format_container(metrics)} · {_format_duration(metrics.get('duration_seconds'))} · {_format_size(metrics.get('size_bytes'))} · {_format_bitrate(metrics.get('overall_bitrate_bps'))}",
        f"- Video: {_format_video_metrics(video)}",
        f"- Audio: {_format_audio_metrics(audio)}",
        f"- Subtitles: {_format_subtitle_metrics(subtitle)} · Chapters: {int(metrics.get('chapter_count', 0) or 0)}",
    ]


def _format_media_comparison_lines(comparison: dict[str, Any]) -> list[str]:
    if not comparison:
        return []
    lines: list[str] = []
    size_ratio = comparison.get("size_ratio")
    overall_bitrate_ratio = comparison.get("overall_bitrate_ratio")
    resolution_scale = comparison.get("resolution_scale")
    if size_ratio not in (None, ""):
        lines.append(f"- Size ratio: {float(size_ratio):.2f}x")
    if overall_bitrate_ratio not in (None, ""):
        lines.append(f"- Overall bitrate ratio: {float(overall_bitrate_ratio):.2f}x")
    if resolution_scale not in (None, ""):
        lines.append(f"- Resolution scale: {float(resolution_scale):.2f}x")
    if comparison.get("container_changed"):
        lines.append("- Container changed during delivery.")
    if comparison.get("video_codec_changed"):
        lines.append("- Video codec changed during delivery.")
    if comparison.get("audio_codec_changed"):
        lines.append("- Audio codec changed during delivery.")
    if comparison.get("subtitle_codec_changed"):
        lines.append("- Subtitle codec changed during delivery.")
    subtitle_stream_delta = comparison.get("subtitle_stream_delta")
    if subtitle_stream_delta not in (None, 0):
        lines.append(f"- Subtitle stream delta: {int(subtitle_stream_delta):+d}")
    chapter_delta = comparison.get("chapter_delta")
    if chapter_delta not in (None, 0):
        lines.append(f"- Chapter delta: {int(chapter_delta):+d}")
    return lines


def _format_container(metrics: dict[str, Any]) -> str:
    return str(metrics.get("container_name") or "unknown").upper()


def _format_duration(value: Any) -> str:
    if value in (None, ""):
        return "unknown duration"
    return f"{float(value):.2f}s"


def _format_size(value: Any) -> str:
    if value in (None, ""):
        return "unknown size"
    return f"{int(value):,} bytes"


def _format_bitrate(value: Any) -> str:
    if value in (None, ""):
        return "unknown bitrate"
    bitrate = float(value)
    if bitrate >= 1_000_000:
        return f"{bitrate / 1_000_000:.2f} Mbps"
    return f"{bitrate / 1_000:.0f} kbps"


def _format_video_metrics(video: dict[str, Any]) -> str:
    codec = str(video.get("codec_name") or "unknown codec")
    width = video.get("width")
    height = video.get("height")
    resolution = (
        f"{int(width)}x{int(height)}"
        if width not in (None, "") and height not in (None, "")
        else "unknown resolution"
    )
    dar = str(video.get("display_aspect_ratio") or "").strip()
    fps = video.get("avg_frame_rate_fps")
    fps_label = f"{float(fps):.2f} fps" if fps not in (None, "") else "unknown fps"
    field_order = str(video.get("field_order") or "unknown").replace("_", " ")
    bitrate = _format_bitrate(video.get("bit_rate_bps"))
    details = [codec, resolution + (f" ({dar})" if dar else ""), fps_label, field_order, bitrate]
    pixel_format = str(video.get("pixel_format") or "").strip()
    if pixel_format:
        details.append(pixel_format)
    return " · ".join(details)


def _format_audio_metrics(audio: dict[str, Any]) -> str:
    codecs = ", ".join(audio.get("codec_names", [])) or "unknown audio"
    stream_count = int(audio.get("stream_count", 0) or 0)
    max_channels = int(audio.get("max_channels", 0) or 0)
    details = [f"{stream_count} stream(s)", codecs]
    if max_channels:
        details.append(f"up to {max_channels} ch")
    languages = ", ".join(audio.get("languages", []))
    if languages:
        details.append(languages)
    return " · ".join(details)


def _format_subtitle_metrics(subtitle: dict[str, Any]) -> str:
    codecs = ", ".join(subtitle.get("codec_names", [])) or "no subtitle codec data"
    stream_count = int(subtitle.get("stream_count", 0) or 0)
    details = [f"{stream_count} stream(s)", codecs]
    languages = ", ".join(subtitle.get("languages", []))
    if languages:
        details.append(languages)
    return " · ".join(details)


def _pick_guidance(guidance: list[str], *needles: str) -> str:
    lowered_needles = tuple(needle.lower() for needle in needles)
    for item in guidance:
        item_lower = item.lower()
        if any(needle in item_lower for needle in lowered_needles):
            return item
    return ""


def _format_ratio_percent(value: float) -> str:
    return f"{value * 100:.0f}% of source"


def _format_resolution(video: dict[str, Any]) -> str:
    width = video.get("width")
    height = video.get("height")
    if width in (None, "") or height in (None, ""):
        return "unknown resolution"
    return f"{int(width)}x{int(height)}"


def build_dashboard_focus_text(overview: dict[str, Any] | None, copy: DashboardCopyConfig) -> str:
    if not overview:
        return copy.focus_empty
    focus_job = overview.get("focus_job")
    if not focus_job:
        return copy.focus_empty
    source_name = str(focus_job.get("source_name", "Selected job"))
    progress_percent = float(focus_job.get("progress", 0.0) or 0.0) * 100.0
    templates = {
        "running": copy.focus_running,
        "failed": copy.focus_failed,
        "paused": copy.focus_paused,
        "queued": copy.focus_queued,
        "planned": copy.focus_planned,
        "completed": copy.focus_completed,
    }
    template = templates.get(str(focus_job.get("status", "")), copy.focus_empty)
    return template.format(source_name=source_name, progress_percent=progress_percent)


class DashboardPage(QWidget):
    def __init__(
        self,
        controller: DesktopController,
        ui_config: DesktopUiConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.ui_config = ui_config
        self._job_lookup: dict[str, dict[str, Any]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel(self.ui_config.copy.dashboard.title)
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        header.addWidget(title)
        refresh_button = QPushButton(self.ui_config.copy.dashboard.refresh_button)
        refresh_button.clicked.connect(self.controller.refresh_dashboard)
        _set_tooltip(refresh_button, self.ui_config.copy.tooltip("dashboard_refresh"))
        header.addStretch(1)
        header.addWidget(refresh_button)
        layout.addLayout(header)

        overview_frame = QFrame()
        overview_frame.setObjectName("panelFrame")
        overview_layout = QVBoxLayout(overview_frame)
        overview_layout.setContentsMargins(16, 16, 16, 16)
        overview_layout.setSpacing(10)

        overview_title = QLabel(self.ui_config.copy.dashboard.overview_title)
        overview_title.setObjectName("sectionTitle")
        overview_layout.addWidget(overview_title)

        progress_header = QHBoxLayout()
        progress_title = QLabel(self.ui_config.copy.dashboard.overall_progress_label)
        progress_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        progress_header.addWidget(progress_title)
        progress_header.addStretch(1)
        self.overall_progress_value = QLabel("0%")
        self.overall_progress_value.setStyleSheet("font-size: 16px; font-weight: 700;")
        progress_header.addWidget(self.overall_progress_value)
        overview_layout.addLayout(progress_header)

        self.overall_progress_bar = QProgressBar()
        self.overall_progress_bar.setRange(0, 100)
        self.overall_progress_bar.setValue(0)
        self.overall_progress_bar.setTextVisible(False)
        overview_layout.addWidget(self.overall_progress_bar)

        self.counts_label = QLabel(self.ui_config.copy.dashboard.queue_idle)
        self.counts_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        overview_layout.addWidget(self.counts_label)

        self.latest_completion_label = QLabel(self.ui_config.copy.dashboard.last_completed_empty)
        self.latest_completion_label.setStyleSheet("color: #9aa8b7;")
        overview_layout.addWidget(self.latest_completion_label)

        focus_title = QLabel(self.ui_config.copy.dashboard.focus_title)
        focus_title.setObjectName("sectionTitle")
        overview_layout.addWidget(focus_title)

        self.focus_label = QLabel(self.ui_config.copy.dashboard.focus_empty)
        self.focus_label.setWordWrap(True)
        self.focus_label.setStyleSheet("color: #9aa8b7;")
        overview_layout.addWidget(self.focus_label)
        layout.addWidget(overview_frame)

        self.selected_job_label = QLabel(self.ui_config.copy.dashboard.selection_empty)
        self.selected_job_label.setStyleSheet("color: #9aa8b7;")
        layout.addWidget(self.selected_job_label)

        highlights_frame = QFrame()
        highlights_frame.setObjectName("panelFrame")
        highlights_layout = QVBoxLayout(highlights_frame)
        highlights_layout.setContentsMargins(16, 16, 16, 16)
        highlights_layout.setSpacing(10)
        highlights_title = QLabel(self.ui_config.copy.dashboard.highlights_title)
        highlights_title.setObjectName("sectionTitle")
        highlights_layout.addWidget(highlights_title)
        self.highlights_row = QHBoxLayout()
        self.highlights_row.setSpacing(10)
        highlights_layout.addLayout(self.highlights_row)
        _set_tooltip(highlights_frame, self.ui_config.copy.tooltip("dashboard_highlights"))
        layout.addWidget(highlights_frame)

        action_row = QHBoxLayout()
        self.resume_button = QPushButton(self.ui_config.copy.dashboard.mark_queued_button)
        self.resume_button.clicked.connect(lambda: self.controller.resume_selected_job(execute=False, execute_degraded=False))
        _set_tooltip(self.resume_button, self.ui_config.copy.tooltip("dashboard_mark_queued"))
        action_row.addWidget(self.resume_button)

        self.run_button = QPushButton(self.ui_config.copy.dashboard.run_selected_button)
        self.run_button.clicked.connect(lambda: self.controller.resume_selected_job(execute=True, execute_degraded=False))
        _set_tooltip(self.run_button, self.ui_config.copy.tooltip("dashboard_run_selected"))
        action_row.addWidget(self.run_button)

        self.degraded_button = QPushButton(self.ui_config.copy.dashboard.retry_degraded_button)
        self.degraded_button.clicked.connect(lambda: self.controller.resume_selected_job(execute=False, execute_degraded=True))
        _set_tooltip(self.degraded_button, self.ui_config.copy.tooltip("dashboard_retry_degraded"))
        action_row.addWidget(self.degraded_button)

        self.view_manifest_button = QPushButton(self.ui_config.copy.dashboard.manifest_button)
        self.view_manifest_button.clicked.connect(self._view_manifest)
        _set_tooltip(self.view_manifest_button, self.ui_config.copy.tooltip("dashboard_view_manifest"))
        action_row.addWidget(self.view_manifest_button)

        self.open_output_button = QPushButton(self.ui_config.copy.dashboard.open_output_button)
        self.open_output_button.clicked.connect(self.controller.open_selected_job_output)
        _set_tooltip(self.open_output_button, self.ui_config.copy.tooltip("dashboard_open_output"))
        action_row.addWidget(self.open_output_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        self._set_action_state("")

        self.jobs_table = QTableWidget(0, 5)
        self.jobs_table.setHorizontalHeaderLabels(["Job", "Source", "Status", "Progress", "Updated"])
        self.jobs_table.verticalHeader().setVisible(False)
        self.jobs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.jobs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.cellDoubleClicked.connect(self._job_activated)
        self.jobs_table.itemSelectionChanged.connect(self._selection_changed)
        _set_tooltip(self.jobs_table, self.ui_config.copy.tooltip("dashboard_jobs_table"))
        layout.addWidget(self.jobs_table, 1)

        run_summary_title = QLabel(self.ui_config.copy.dashboard.run_summary_title)
        run_summary_title.setObjectName("sectionTitle")
        layout.addWidget(run_summary_title)

        metrics_title = QLabel(self.ui_config.copy.dashboard.metrics_title)
        metrics_title.setObjectName("sectionTitle")
        layout.addWidget(metrics_title)

        metrics_frame = QFrame()
        metrics_frame.setObjectName("panelFrame")
        metrics_layout = QVBoxLayout(metrics_frame)
        metrics_layout.setContentsMargins(14, 14, 14, 14)
        metrics_layout.setSpacing(10)

        self.metrics_table = QTableWidget(0, 3)
        self.metrics_table.setHorizontalHeaderLabels(
            [
                self.ui_config.copy.dashboard.metrics_metric_label,
                self.ui_config.copy.dashboard.metrics_before_label,
                self.ui_config.copy.dashboard.metrics_after_label,
            ]
        )
        self.metrics_table.verticalHeader().setVisible(False)
        self.metrics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metrics_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.metrics_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.metrics_table.setMinimumHeight(200)
        self.metrics_table.horizontalHeader().setStretchLastSection(True)
        metrics_layout.addWidget(self.metrics_table)

        guidance_title = QLabel(self.ui_config.copy.dashboard.metrics_guidance_title)
        guidance_title.setObjectName("sectionTitle")
        metrics_layout.addWidget(guidance_title)

        self.metrics_guidance_view = QTextEdit()
        self.metrics_guidance_view.setReadOnly(True)
        self.metrics_guidance_view.setMinimumHeight(88)
        self.metrics_guidance_view.setPlainText(self.ui_config.copy.dashboard.metrics_empty)
        metrics_layout.addWidget(self.metrics_guidance_view)
        layout.addWidget(metrics_frame)

        self.run_summary_view = QTextEdit()
        self.run_summary_view.setReadOnly(True)
        self.run_summary_view.setMinimumHeight(140)
        self.run_summary_view.setPlainText(self.ui_config.copy.dashboard.run_summary_empty)
        layout.addWidget(self.run_summary_view)

        self.manifest_view = QTextEdit()
        self.manifest_view.setReadOnly(True)
        self.manifest_view.setPlainText(self.ui_config.copy.dashboard.manifest_empty)
        layout.addWidget(self.manifest_view, 1)

        review_title = QLabel(self.ui_config.copy.dashboard.result_review_title)
        review_title.setObjectName("sectionTitle")
        layout.addWidget(review_title)

        review_header = QHBoxLayout()
        self.review_mode = QComboBox()
        self.review_mode.addItems(list(self.ui_config.preview.comparison_modes))
        _set_tooltip(self.review_mode, self.ui_config.copy.tooltip("dashboard_review_mode"))
        review_header.addWidget(QLabel(self.ui_config.copy.dashboard.compare_label))
        review_header.addWidget(self.review_mode)
        review_header.addStretch(1)
        layout.addLayout(review_header)

        self.review_compare = PreviewCompareWidget(tooltips=self.ui_config.copy.tooltips)
        self.review_compare.setMinimumHeight(260)
        self.review_mode.currentTextChanged.connect(self.review_compare.set_comparison_mode)
        layout.addWidget(self.review_compare, 1)

    def apply_snapshot(self, payload: dict[str, Any], selected_job_id: str) -> None:
        overview = dict(payload.get("overview", {}))
        overall_progress_percent = int(round(float(overview.get("overall_progress", 0.0) or 0.0) * 100.0))
        self.overall_progress_bar.setValue(overall_progress_percent)
        self.overall_progress_value.setText(f"{overall_progress_percent}%")
        if int(overview.get("total_jobs", 0) or 0) <= 0:
            self.counts_label.setText(self.ui_config.copy.dashboard.overview_empty)
        else:
            self.counts_label.setText(
                f"{self.ui_config.copy.dashboard.active_label}: {overview.get('active_job_count', 0)} | "
                f"{self.ui_config.copy.dashboard.completed_label}: {overview.get('completed_job_count', 0)} | "
                f"{self.ui_config.copy.dashboard.issues_label}: {overview.get('issue_job_count', 0)}"
            )
        latest_completed = overview.get("latest_completed_job")
        if latest_completed:
            self.latest_completion_label.setText(
                self.ui_config.copy.dashboard.last_completed_template.format(
                    source_name=str(latest_completed.get("source_name", "Completed job"))
                )
            )
        else:
            self.latest_completion_label.setText(self.ui_config.copy.dashboard.last_completed_empty)
        self.focus_label.setText(build_dashboard_focus_text(overview, self.ui_config.copy.dashboard))
        jobs = list(payload.get("jobs", []))
        self._job_lookup = {job["job_id"]: job for job in jobs}
        self.jobs_table.setRowCount(len(jobs))
        for row_index, job in enumerate(jobs):
            values = [
                job["job_id"][:8],
                Path(job["source_path"]).name,
                job["status"],
                f"{job['progress'] * 100:.0f}%",
                job["updated_at"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job["job_id"])
                if column == 2:
                    item.setForeground(self._status_brush(job["status"]))
                self.jobs_table.setItem(row_index, column, item)
            if job["job_id"] == selected_job_id:
                self.jobs_table.selectRow(row_index)
        self._set_action_state(selected_job_id)

    def apply_run_manifest(self, payload: dict[str, Any] | None) -> None:
        if payload is None:
            self._apply_highlights(None)
            self._apply_metrics_snapshot(None)
            self.run_summary_view.setPlainText(self.ui_config.copy.dashboard.run_summary_empty)
            self.manifest_view.setPlainText(self.ui_config.copy.dashboard.manifest_empty)
            self.selected_job_label.setText(self.ui_config.copy.dashboard.selection_empty)
            self.review_compare.clear_preview()
            return
        job_id = self.controller.session.selected_job_id
        execution_mode = payload.get("encode_settings", {}).get("execution_mode", "not run yet")
        self.selected_job_label.setText(f"Selected job {job_id[:8]} · {execution_mode}")
        self._apply_highlights(payload)
        self._apply_metrics_snapshot(payload)
        self.run_summary_view.setPlainText(build_run_summary(payload))
        self.manifest_view.setPlainText(json.dumps(payload, indent=2, sort_keys=True))
        self._load_review_media(job_id, payload)

    def _apply_highlights(self, payload: dict[str, Any] | None) -> None:
        highlights = build_media_change_highlights(payload)
        self._clear_highlights()
        if not highlights:
            empty_label = QLabel(self.ui_config.copy.dashboard.highlights_empty)
            empty_label.setWordWrap(True)
            empty_label.setStyleSheet("color: #9aa8b7;")
            self.highlights_row.addWidget(empty_label, 1)
            return
        for highlight in highlights:
            card = QFrame()
            card.setObjectName("panelFrame")
            card.setMinimumHeight(92)
            card.setToolTip(str(highlight.get("detail", "")))
            card.setStyleSheet(self._highlight_card_style(str(highlight.get("tone", "info"))))
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            title = QLabel(str(highlight.get("title", "")))
            title.setStyleSheet("font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #9aa8b7;")
            card_layout.addWidget(title)
            value = QLabel(str(highlight.get("value", "")))
            value.setWordWrap(True)
            value.setStyleSheet("font-size: 18px; font-weight: 700; color: #f4f8fb;")
            card_layout.addWidget(value, 1)
            self.highlights_row.addWidget(card, 1)

    def _clear_highlights(self) -> None:
        while self.highlights_row.count():
            item = self.highlights_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _highlight_card_style(self, tone: str) -> str:
        accents = {
            "success": "#2f9e74",
            "warning": "#d8a93d",
            "danger": "#c75d5d",
            "info": "#4d86c7",
        }
        accent = accents.get(tone, accents["info"])
        return (
            "QFrame#panelFrame {"
            "background-color: rgba(19, 25, 32, 0.94);"
            "border: 1px solid rgba(255, 255, 255, 0.07);"
            f"border-left: 3px solid {accent};"
            "border-radius: 14px;"
            "}"
        )

    def _apply_metrics_snapshot(self, payload: dict[str, Any] | None) -> None:
        snapshot = build_media_metrics_snapshot(payload)
        rows = list(snapshot.get("rows", []))
        guidance = [str(item).strip() for item in snapshot.get("guidance", []) if str(item).strip()]
        self.metrics_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            metric, before, after = row
            for column, value in enumerate((metric, before, after)):
                self.metrics_table.setItem(row_index, column, QTableWidgetItem(value))
        if not rows:
            self.metrics_guidance_view.setPlainText(self.ui_config.copy.dashboard.metrics_empty)
            return
        if guidance:
            self.metrics_guidance_view.setPlainText("\n".join(f"- {line}" for line in guidance))
        else:
            self.metrics_guidance_view.setPlainText(self.ui_config.copy.dashboard.metrics_guidance_empty)

    def _job_activated(self, row: int, _: int) -> None:
        item = self.jobs_table.item(row, 0)
        if item is None:
            return
        job_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if job_id:
            self.controller.select_job(job_id)

    def _selection_changed(self) -> None:
        items = self.jobs_table.selectedItems()
        if not items:
            self._set_action_state("")
            return
        job_id = str(items[0].data(Qt.ItemDataRole.UserRole) or "")
        if job_id:
            self.controller.select_job(job_id)
            self._set_action_state(job_id)

    def _set_action_state(self, job_id: str) -> None:
        enabled = bool(job_id)
        self.resume_button.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
        self.degraded_button.setEnabled(enabled)
        self.view_manifest_button.setEnabled(enabled)
        self.open_output_button.setEnabled(enabled)

    def _view_manifest(self) -> None:
        payload = self.controller.run_manifest_payload
        if payload is None:
            return
        PayloadViewerDialog("Run Manifest", payload, self).exec()

    def _load_review_media(self, job_id: str, payload: dict[str, Any]) -> None:
        job = self._job_lookup.get(job_id)
        if job is None:
            self.review_compare.clear_preview()
            return
        output_files = list(payload.get("output_files", []))
        if not output_files:
            self.review_compare.clear_preview()
            return
        source_path = str(job.get("source_path", ""))
        processed_path = str(output_files[0])
        if not source_path or not processed_path:
            self.review_compare.clear_preview()
            return
        self.review_compare.set_comparison_mode(self.review_mode.currentText())
        self.review_compare.load_preview(
            {
                "comparison_artifacts": {
                    "source": source_path,
                    "processed": processed_path,
                },
                "fidelity_mode": "final_output",
                "warnings": [
                    f"Reviewing completed output via {payload.get('encode_settings', {}).get('execution_mode', 'unknown mode')}.",
                ],
            },
            auto_play=False,
        )

    def _status_brush(self, status: str):
        palette = {
            "completed": QBrush(QColor(self.ui_config.theme.success_color)),
            "running": QBrush(QColor(self.ui_config.theme.info_color)),
            "queued": QBrush(QColor(self.ui_config.theme.warning_color)),
            "planned": QBrush(QColor(self.ui_config.theme.muted_color)),
            "paused": QBrush(QColor(self.ui_config.theme.warning_color)),
            "failed": QBrush(QColor(self.ui_config.theme.danger_color)),
        }
        return palette.get(status, QBrush(QColor(self.ui_config.theme.ink_color)))


class DesktopMainWindow(QMainWindow):
    def __init__(self, controller: DesktopController, ui_config: DesktopUiConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.ui_config = ui_config
        self._page_map: dict[str, int] = {}
        self._build_ui()
        self._connect_signals()
        self._apply_theme()
        self.controller.initialize()

    def _build_ui(self) -> None:
        self.setWindowTitle(self.ui_config.window.title)
        self.resize(self.ui_config.window.width, self.ui_config.window.height)
        self.setMinimumSize(self.ui_config.window.minimum_width, self.ui_config.window.minimum_height)
        icon_path = _resolve_desktop_asset(self.ui_config, "app_icon")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        wordmark = QLabel(self.ui_config.copy.global_text.wordmark)
        wordmark.setStyleSheet("font-size: 26px; font-weight: 800;")
        _set_tooltip(wordmark, self.ui_config.copy.tooltip("window_wordmark"))
        header.addWidget(wordmark)

        self.busy_label = QLabel(self.ui_config.copy.global_text.ready_label)
        self.busy_label.setStyleSheet("color: #5b6670;")
        header.addWidget(self.busy_label)
        header.addStretch(1)

        self.doctor_button = QPushButton(self.ui_config.copy.global_text.doctor_button)
        self.model_button = QPushButton(self.ui_config.copy.global_text.model_button)
        self.install_button = QPushButton(self.ui_config.copy.global_text.install_button)
        self.doctor_button.clicked.connect(self.controller.run_doctor)
        self.model_button.clicked.connect(self.controller.refresh_model_packs)
        self.install_button.clicked.connect(self.controller.install_recommended_models)
        _set_tooltip(self.doctor_button, self.ui_config.copy.tooltip("header_doctor_button"))
        _set_tooltip(self.model_button, self.ui_config.copy.tooltip("header_model_button"))
        _set_tooltip(self.install_button, self.ui_config.copy.tooltip("header_install_button"))
        header.addWidget(self.doctor_button)
        header.addWidget(self.model_button)
        header.addWidget(self.install_button)
        layout.addLayout(header)

        nav = QHBoxLayout()
        self.nav_buttons: dict[str, QPushButton] = {}
        for page in ["ingest", "summary", "workspace", "dashboard"]:
            button = QPushButton(page.replace("_", " ").title())
            button.clicked.connect(lambda _checked=False, page_id=page: self.controller.set_page(page_id))
            _set_tooltip(button, self.ui_config.copy.tooltip(f"nav_{page}"))
            self.nav_buttons[page] = button
            nav.addWidget(button)
        nav.addStretch(1)
        layout.addLayout(nav)

        self.pages = QStackedWidget()
        self.ingest_page = IngestPage(self.controller, self.ui_config)
        self.summary_page = SummaryPage(self.controller, self.ui_config)
        self.workspace_page = WorkspacePage(self.controller, self.ui_config)
        self.dashboard_page = DashboardPage(self.controller, self.ui_config)
        for page_id, page in [
            ("ingest", self.ingest_page),
            ("summary", self.summary_page),
            ("workspace", self.workspace_page),
            ("dashboard", self.dashboard_page),
        ]:
            self._page_map[page_id] = self.pages.addWidget(page)
        layout.addWidget(self.pages, 1)

        self.queue_bar = QueueBar(
            self.ui_config.layout.queue_bar_expanded_height,
            self.ui_config.copy.queue,
            tooltips=self.ui_config.copy.tooltips,
        )
        self.queue_bar.jobActivated.connect(self._queue_job_activated)
        self.queue_bar.collapsedChanged.connect(self.controller.set_queue_collapsed)
        self.queue_bar.setVisible(False)
        layout.addWidget(self.queue_bar)

        self.setCentralWidget(root)

        self.dashboard_timer = QTimer(self)
        self.dashboard_timer.setInterval(self.ui_config.behavior.dashboard_refresh_seconds * 1000)
        self.dashboard_timer.timeout.connect(self.controller.refresh_dashboard)
        self.dashboard_timer.start()

    def _connect_signals(self) -> None:
        self.controller.sessionChanged.connect(self._apply_session)
        self.controller.projectChanged.connect(self._apply_project)
        self.controller.previewChanged.connect(self.workspace_page.apply_preview)
        self.controller.dashboardChanged.connect(self._apply_dashboard)
        self.controller.runManifestChanged.connect(self.dashboard_page.apply_run_manifest)
        self.controller.runtimeStatusChanged.connect(self.ingest_page.apply_runtime_status)
        self.controller.recentTargetsChanged.connect(self.ingest_page.apply_recent_targets)
        self.controller.doctorReportChanged.connect(
            lambda payload: PayloadViewerDialog(self.ui_config.copy.global_text.doctor_dialog_title, payload, self).exec()
        )
        self.controller.modelPacksChanged.connect(
            lambda payload: PayloadViewerDialog(self.ui_config.copy.global_text.model_dialog_title, payload, self).exec()
        )
        self.controller.supportBundleReady.connect(
            lambda payload: PayloadViewerDialog(self.ui_config.copy.global_text.support_dialog_title, payload, self).exec()
        )
        self.controller.busyChanged.connect(self._set_busy)
        self.controller.messageChanged.connect(self._show_message)
        self.controller.errorRaised.connect(self._show_error)
        self.controller.pageRequested.connect(self._switch_page)

    def _apply_theme(self) -> None:
        theme = self.ui_config.theme
        self.setStyleSheet(
            f"""
            QWidget {{
                color: {theme.ink_color};
                background: {theme.background_start};
                font-family: "{theme.font_family}";
            }}
            QMainWindow {{
                background: {theme.background_start};
            }}
            QStatusBar {{
                background: {theme.surface_alt};
                border-top: 1px solid {theme.line_color};
            }}
            QFrame#dropTarget {{
                border: 2px dashed {theme.accent_color};
                border-radius: 18px;
                background: {theme.surface_alt};
            }}
            QFrame#panelFrame, QFrame#previewPanel {{
                background: {theme.panel_color};
                border: 1px solid {theme.line_color};
                border-radius: 16px;
            }}
            QFrame#stageCard {{
                background: {theme.panel_raised};
                border: 1px solid {theme.line_color};
                border-radius: 14px;
            }}
            QFrame#stageCard[selected="true"] {{
                border: 1px solid {theme.accent_color};
                background: {theme.accent_soft};
            }}
            QLabel#stageCardTitle {{
                font-family: "{theme.display_font_family}";
                font-size: 14px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#stageCardStatus {{
                background: {theme.surface_alt};
                border: 1px solid {theme.line_color};
                border-radius: 9px;
                color: {theme.muted_color};
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 700;
            }}
            QLabel#stageCardSummary {{
                color: {theme.muted_color};
                background: transparent;
                font-size: 12px;
            }}
            QLabel#sectionTitle {{
                font-family: "{theme.display_font_family}";
                font-size: 13px;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                color: {theme.muted_color};
                background: transparent;
            }}
            QPushButton {{
                background: {theme.surface_color};
                border: 1px solid {theme.line_color};
                border-radius: 10px;
                padding: 10px 14px;
            }}
            QPushButton:hover {{
                border-color: {theme.accent_color};
            }}
            QPushButton:checked {{
                background: {theme.accent_soft};
                border-color: {theme.accent_color};
            }}
            QTextEdit, QLineEdit, QComboBox, QListWidget, QTableWidget, QSpinBox, QDoubleSpinBox {{
                background: {theme.surface_color};
                border: 1px solid {theme.line_color};
                border-radius: 10px;
                padding: 6px;
            }}
            QProgressBar {{
                background: {theme.surface_alt};
                border: 1px solid {theme.line_color};
                border-radius: 8px;
                min-height: 10px;
                max-height: 10px;
            }}
            QProgressBar::chunk {{
                background: {theme.accent_color};
                border-radius: 7px;
            }}
            QToolTip {{
                color: {theme.ink_color};
                background: {theme.surface_alt};
                border: 1px solid {theme.line_color};
                padding: 6px 8px;
            }}
            QListWidget {{
                background: transparent;
                border: none;
            }}
            QTableWidget {{
                gridline-color: {theme.line_color};
                selection-background-color: {theme.accent_soft};
            }}
            QHeaderView::section {{
                background: {theme.surface_alt};
                color: {theme.muted_color};
                border: none;
                border-bottom: 1px solid {theme.line_color};
                padding: 8px;
                font-weight: 700;
            }}
            """
        )

    def _apply_session(self, session: DesktopSessionState) -> None:
        self.ingest_page.apply_session(session)
        self.workspace_page.apply_session(session)
        self.queue_bar.set_collapsed(session.queue_collapsed)
        self._switch_page(session.current_page)
        for page_id, button in self.nav_buttons.items():
            button.setEnabled(page_id == "ingest" or session.last_target != "")
            button.setStyleSheet("font-weight: 700;" if page_id == session.current_page else "")

    def _apply_project(self, payload: dict[str, Any] | None) -> None:
        self.summary_page.apply_project(payload)
        self.workspace_page.apply_project(payload)

    def _apply_dashboard(self, payload: dict[str, Any]) -> None:
        selected_job_id = self.controller.session.selected_job_id
        self.queue_bar.apply_snapshot(payload, selected_job_id)
        self.dashboard_page.apply_snapshot(payload, selected_job_id)
        active_statuses = {"queued", "running", "failed", "paused", "planned"}
        self.queue_bar.setVisible(any(job.get("status") in active_statuses for job in payload.get("jobs", [])))

    def _switch_page(self, page_id: str) -> None:
        index = self._page_map.get(page_id, self._page_map["ingest"])
        self.pages.setCurrentIndex(index)

    def _set_busy(self, busy: bool) -> None:
        self.doctor_button.setEnabled(not busy)
        self.model_button.setEnabled(not busy)
        self.install_button.setEnabled(not busy)
        self.ingest_page.support_bundle_button.setEnabled(not busy)
        self.busy_label.setText(
            self.ui_config.copy.global_text.working_label
            if busy
            else self.ui_config.copy.global_text.ready_label
        )

    def _show_message(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)
        self.busy_label.setText(message)

    def _show_error(self, detail: str) -> None:
        QMessageBox.critical(self, self.ui_config.copy.global_text.error_dialog_title, detail)

    def _queue_job_activated(self, job_id: str) -> None:
        self.controller.select_job(job_id)
        self.controller.set_page("dashboard")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.workspace_page.preview_compare.clear_preview()
        self.dashboard_page.review_compare.clear_preview()
        self.controller.shutdown()
        super().closeEvent(event)


def run_desktop_app(argv: list[str] | None = None) -> int:
    args = argv or sys.argv
    app = QApplication(args)
    ui_config = load_ui_config()
    icon_path = _resolve_desktop_asset(ui_config, "app_icon")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    controller = DesktopController(ui_config=ui_config)
    window = DesktopMainWindow(controller, ui_config)
    window.show()
    return app.exec()
