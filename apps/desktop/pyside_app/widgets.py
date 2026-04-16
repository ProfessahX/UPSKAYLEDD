from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from pyside_app.ui_config import QueueCopyConfig


def build_queue_summary(payload: dict[str, Any], copy: QueueCopyConfig) -> str:
    counts = dict(payload.get("counts", {}))
    overview = dict(payload.get("overview", {}))
    focus_job = overview.get("focus_job") or {}
    summary_counts = copy.summary_counts_template.format(
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
    )
    if not focus_job:
        return copy.idle

    source_name = str(focus_job.get("source_name", "Selected job"))
    progress_percent = float(focus_job.get("progress", 0.0) or 0.0) * 100.0
    status = str(focus_job.get("status", "queued"))
    if status == "running":
        return f"{copy.processing_template.format(source_name=source_name, progress_percent=progress_percent)} | {summary_counts}"
    if status in {"queued", "planned"}:
        return f"{copy.waiting_template.format(source_name=source_name)} | {summary_counts}"
    return f"{copy.attention_template.format(source_name=source_name, status_label=status.replace('_', ' '))} | {summary_counts}"


class DropTargetFrame(QFrame):
    pathDropped = Signal(str)

    def __init__(self, title: str, subtitle: str, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropTarget")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        if tooltip:
            self.setToolTip(tooltip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 28px; font-weight: 700;")
        layout.addWidget(heading)

        copy = QLabel(subtitle)
        copy.setWordWrap(True)
        copy.setStyleSheet("font-size: 14px; color: #5b6670;")
        layout.addWidget(copy)

        hint = QLabel("Drag a file or folder here")
        hint.setStyleSheet("font-size: 18px; font-weight: 600; color: #b64f1d;")
        layout.addWidget(hint)
        layout.addStretch(1)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if not urls:
            event.ignore()
            return
        self.pathDropped.emit(urls[0].toLocalFile())
        event.acceptProposedAction()


class PayloadViewerDialog(QDialog):
    def __init__(self, title: str, payload: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(880, 620)

        layout = QVBoxLayout(self)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        viewer.setPlainText(json.dumps(payload, indent=2, sort_keys=True))
        layout.addWidget(viewer, 1)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


class StageCardWidget(QFrame):
    def __init__(
        self,
        *,
        title: str,
        status: str,
        summary: str,
        tooltip: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("stageCard")
        if tooltip:
            self.setToolTip(tooltip)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("stageCardTitle")
        header.addWidget(self.title_label, 1)

        self.status_label = QLabel(status)
        self.status_label.setObjectName("stageCardStatus")
        header.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)

        self.summary_label = QLabel(summary)
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("stageCardSummary")
        layout.addWidget(self.summary_label)

    def update_content(self, *, title: str, status: str, summary: str) -> None:
        self.title_label.setText(title)
        self.status_label.setText(status)
        self.summary_label.setText(summary)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class QueueBar(QWidget):
    jobActivated = Signal(str)
    collapsedChanged = Signal(bool)

    def __init__(
        self,
        expanded_height: int,
        copy: QueueCopyConfig,
        *,
        tooltips: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._expanded_height = expanded_height
        self._collapsed = False
        self.copy = copy
        self.tooltips = tooltips or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.toggle_button = QPushButton(self.copy.collapse_button)
        self.toggle_button.clicked.connect(self._toggle)
        self.toggle_button.setToolTip(self.tooltips.get("queue_toggle", ""))
        header.addWidget(self.toggle_button)

        self.summary_label = QLabel(self.copy.idle)
        self.summary_label.setStyleSheet("font-weight: 600;")
        header.addWidget(self.summary_label, 1)
        layout.addLayout(header)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Job", "Source", "Status", "Progress"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._activate_row)
        self.table.setMinimumHeight(self._expanded_height)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setToolTip(self.tooltips.get("queue_table", ""))
        layout.addWidget(self.table, 1)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.table.setVisible(not collapsed)
        self.toggle_button.setText(self.copy.expand_button if collapsed else self.copy.collapse_button)

    def apply_snapshot(self, payload: dict[str, Any], selected_job_id: str = "") -> None:
        jobs = list(payload.get("jobs", []))
        self.summary_label.setText(build_queue_summary(payload, self.copy))

        self.table.setRowCount(len(jobs))
        for row_index, job in enumerate(jobs):
            source_name = Path(job["source_path"]).name
            values = [
                job["job_id"][:8],
                source_name,
                job["status"],
                f"{job['progress'] * 100:.0f}%",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, job["job_id"])
                self.table.setItem(row_index, column, item)
            if job["job_id"] == selected_job_id:
                self.table.selectRow(row_index)

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)
        self.collapsedChanged.emit(self._collapsed)

    def _activate_row(self, row: int, _: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        job_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if job_id:
            self.jobActivated.emit(job_id)


class PreviewCompareWidget(QWidget):
    def __init__(self, *, tooltips: dict[str, str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "slider_wipe"
        self._ab_show_processed = True
        self._sync_guard = False
        self.tooltips = tooltips or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_widget = QVideoWidget()
        self.processed_widget = QVideoWidget()
        self.source_widget.setStyleSheet("background: #0f1720; border-radius: 12px;")
        self.processed_widget.setStyleSheet("background: #0f1720; border-radius: 12px;")
        self.splitter.addWidget(self.source_widget)
        self.splitter.addWidget(self.processed_widget)
        self.splitter.setSizes([1, 1])
        layout.addWidget(self.splitter, 1)

        controls = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.pause_button = QPushButton("Pause")
        self.restart_button = QPushButton("Restart")
        self.ab_source_button = QPushButton("Show Source")
        self.ab_processed_button = QPushButton("Show Processed")
        self.wipe_slider = QSlider(Qt.Orientation.Horizontal)
        self.wipe_slider.setRange(10, 90)
        self.wipe_slider.setValue(50)

        self.play_button.clicked.connect(self.play)
        self.pause_button.clicked.connect(self.pause)
        self.restart_button.clicked.connect(self.restart)
        self.ab_source_button.clicked.connect(lambda: self._set_ab_focus(False))
        self.ab_processed_button.clicked.connect(lambda: self._set_ab_focus(True))
        self.wipe_slider.valueChanged.connect(self._apply_mode_layout)
        self.play_button.setToolTip(self.tooltips.get("preview_play", ""))
        self.pause_button.setToolTip(self.tooltips.get("preview_pause", ""))
        self.restart_button.setToolTip(self.tooltips.get("preview_restart", ""))
        self.ab_source_button.setToolTip(self.tooltips.get("preview_ab_source", ""))
        self.ab_processed_button.setToolTip(self.tooltips.get("preview_ab_processed", ""))
        self.wipe_slider.setToolTip(self.tooltips.get("preview_wipe", ""))

        controls.addWidget(self.play_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.restart_button)
        controls.addWidget(self.ab_source_button)
        controls.addWidget(self.ab_processed_button)
        controls.addWidget(QLabel("Wipe"))
        controls.addWidget(self.wipe_slider, 1)
        layout.addLayout(controls)

        self.status_label = QLabel("Preview is idle.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #5b6670;")
        layout.addWidget(self.status_label)

        self.source_audio = QAudioOutput()
        self.processed_audio = QAudioOutput()
        self.source_audio.setVolume(0.0)
        self.processed_audio.setVolume(0.0)

        self.source_player = QMediaPlayer(self)
        self.processed_player = QMediaPlayer(self)
        self.source_player.setAudioOutput(self.source_audio)
        self.processed_player.setAudioOutput(self.processed_audio)
        self.source_player.setVideoOutput(self.source_widget)
        self.processed_player.setVideoOutput(self.processed_widget)

        self.source_player.positionChanged.connect(self._sync_from_source)
        self.processed_player.positionChanged.connect(self._sync_from_processed)
        self.source_player.playbackStateChanged.connect(self._sync_playback_state)
        self.processed_player.playbackStateChanged.connect(self._sync_playback_state)

        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(250)
        self.sync_timer.timeout.connect(self._reconcile_positions)
        self.sync_timer.start()

        self._apply_mode_layout()

    def set_comparison_mode(self, mode: str) -> None:
        self._mode = mode
        self._apply_mode_layout()

    def load_preview(self, payload: dict[str, Any], auto_play: bool = False) -> None:
        artifacts = dict(payload.get("comparison_artifacts", {}))
        source_path = artifacts.get("source")
        processed_path = artifacts.get("processed")

        self.source_player.stop()
        self.processed_player.stop()
        if source_path and Path(source_path).exists():
            self.source_player.setSource(QUrl.fromLocalFile(source_path))
        else:
            self.source_player.setSource(QUrl())
        if processed_path and Path(processed_path).exists():
            self.processed_player.setSource(QUrl.fromLocalFile(processed_path))
        else:
            self.processed_player.setSource(QUrl())

        fidelity = payload.get("fidelity_mode", "unknown")
        warnings = payload.get("warnings", [])
        warning_summary = " | ".join(warnings[:3]) if warnings else "No preview warnings."
        self.status_label.setText(f"Preview ready ({fidelity}). {warning_summary}")
        self._apply_mode_layout()
        if auto_play:
            self.play()

    def clear_preview(self) -> None:
        self.source_player.stop()
        self.processed_player.stop()
        self.source_player.setSource(QUrl())
        self.processed_player.setSource(QUrl())
        self.status_label.setText("Preview is idle.")

    def play(self) -> None:
        if self.source_player.source().isEmpty() and self.processed_player.source().isEmpty():
            return
        if not self.source_player.source().isEmpty():
            self.source_player.play()
        if not self.processed_player.source().isEmpty():
            self.processed_player.play()

    def pause(self) -> None:
        self.source_player.pause()
        self.processed_player.pause()

    def restart(self) -> None:
        self.source_player.setPosition(0)
        self.processed_player.setPosition(0)
        self.play()

    def _set_ab_focus(self, show_processed: bool) -> None:
        self._ab_show_processed = show_processed
        self._apply_mode_layout()

    def _apply_mode_layout(self) -> None:
        self.ab_source_button.setVisible(self._mode == "ab_toggle")
        self.ab_processed_button.setVisible(self._mode == "ab_toggle")
        self.wipe_slider.setEnabled(self._mode == "slider_wipe")

        if self._mode == "side_by_side":
            self.source_widget.setVisible(True)
            self.processed_widget.setVisible(True)
            self.splitter.setSizes([500, 500])
            return

        if self._mode == "ab_toggle":
            self.source_widget.setVisible(True)
            self.processed_widget.setVisible(True)
            self.splitter.setSizes([0, 1000] if self._ab_show_processed else [1000, 0])
            return

        ratio = self.wipe_slider.value() / 100.0
        left = max(1, int(1000 * ratio))
        right = max(1, 1000 - left)
        self.source_widget.setVisible(True)
        self.processed_widget.setVisible(True)
        self.splitter.setSizes([left, right])

    def _sync_playback_state(self) -> None:
        if self._sync_guard:
            return
        self._sync_guard = True
        try:
            processed_state = self.processed_player.playbackState()
            source_state = self.source_player.playbackState()
            if processed_state != source_state:
                if processed_state == QMediaPlayer.PlaybackState.PlayingState:
                    self.source_player.play()
                elif processed_state == QMediaPlayer.PlaybackState.PausedState:
                    self.source_player.pause()
        finally:
            self._sync_guard = False

    def _sync_from_source(self, position: int) -> None:
        if self._sync_guard or self.processed_player.source().isEmpty():
            return
        self._sync_guard = True
        try:
            if abs(self.processed_player.position() - position) > 120:
                self.processed_player.setPosition(position)
        finally:
            self._sync_guard = False

    def _sync_from_processed(self, position: int) -> None:
        if self._sync_guard or self.source_player.source().isEmpty():
            return
        self._sync_guard = True
        try:
            if abs(self.source_player.position() - position) > 120:
                self.source_player.setPosition(position)
        finally:
            self._sync_guard = False

    def _reconcile_positions(self) -> None:
        if self.source_player.source().isEmpty() or self.processed_player.source().isEmpty():
            return
        difference = abs(self.source_player.position() - self.processed_player.position())
        if difference > 120:
            self.processed_player.setPosition(self.source_player.position())
