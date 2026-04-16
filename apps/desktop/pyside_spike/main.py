from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from upskayledd.app_service import AppService

try:
    from PySide6.QtCore import Qt, QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPushButton,
        QSplitter,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - runtime-only shell helper
    raise SystemExit(
        "PySide6 is not installed yet. Install it for the native shell spike, then rerun this file."
    ) from exc


class SpikeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.service = AppService()
        self.setWindowTitle("UPSKAYLEDD PySide6 Spike")
        self.resize(1440, 860)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(14)

        title = QLabel("UPSKAYLEDD Native Shell Spike")
        title.setStyleSheet("font-size: 28px; font-weight: 700;")
        subtitle = QLabel(
            "Thin native shell proving that the desktop can drive the shared Python engine without bypassing it."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #5a616c; font-size: 14px;")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls_panel())
        splitter.addWidget(self._build_preview_panel())
        splitter.addWidget(self._build_output_panel())
        splitter.setSizes([340, 520, 520])
        root_layout.addWidget(splitter, 1)

        self.setCentralWidget(root)

    def _build_controls_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        section = QLabel("Control Rail")
        section.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(section)

        buttons = [
            ("Run Doctor", self._show_doctor),
            ("List Model Packs", self._show_model_packs),
            ("Show Shell Criteria", self._show_decision_gate_notes),
        ]
        for label, handler in buttons:
            button = QPushButton(label)
            button.clicked.connect(handler)
            button.setMinimumHeight(42)
            layout.addWidget(button)

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText(r"Source path for preview, e.g. Z:\media\legacy_episode_sample.mkv")
        layout.addWidget(self.source_input)

        self.stage_picker = QComboBox()
        self.stage_picker.addItems(["cleanup", "upscale"])
        layout.addWidget(self.stage_picker)

        preview_button = QPushButton("Generate Exact Preview Metadata")
        preview_button.clicked.connect(self._generate_preview)
        preview_button.setMinimumHeight(42)
        layout.addWidget(preview_button)

        note = QLabel(
            "This spike intentionally stays thin. The engine, queue, preview, and validator still live in shared Python modules."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #5a616c;")
        layout.addWidget(note)
        layout.addStretch(1)
        return panel

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        section = QLabel("Preview Surface")
        section.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(section)

        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background: #0f1720; border-radius: 14px;")
        layout.addWidget(self.video_widget, 1)

        self.preview_status = QLabel(
            "Preview playback is idle. Generate preview metadata from the control rail to load the processed clip here."
        )
        self.preview_status.setWordWrap(True)
        self.preview_status.setStyleSheet("color: #5a616c;")
        layout.addWidget(self.preview_status)

        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(0.0)
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        return panel

    def _build_output_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)

        section = QLabel("Service Output")
        section.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(section)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 12px;")
        layout.addWidget(self.output, 1)
        return panel

    def _show_doctor(self) -> None:
        self.output.setPlainText(json.dumps(self.service.doctor_report(), indent=2, sort_keys=True))

    def _show_model_packs(self) -> None:
        self.output.setPlainText(json.dumps(self.service.list_model_packs(), indent=2, sort_keys=True))

    def _show_decision_gate_notes(self) -> None:
        payload = {
            "decision_gate": [
                "synced video preview quality and responsiveness",
                "ease of building the three-zone layout",
                "packaging/bootstrap complexity",
                "cross-platform hardware/process integration",
                "developer velocity for dashboard/workspace UX",
            ],
            "service_boundary": "Desktop shells call AppService; they do not invoke ffmpeg, ffprobe, VapourSynth, or vs-mlrt directly.",
        }
        self.output.setPlainText(json.dumps(payload, indent=2, sort_keys=True))

    def _generate_preview(self) -> None:
        source_path = self.source_input.text().strip()
        if not source_path:
            self.output.setPlainText("Provide a source path before generating preview metadata.")
            return
        stage_id = self.stage_picker.currentText()
        stage_settings = {}
        if stage_id == "upscale":
            stage_settings = {"target_width": 1280, "target_height": 720}
        result = self.service.prepare_preview(
            source_path=source_path,
            stage_id=stage_id,
            comparison_mode=module_comparison_mode(),
            stage_settings=stage_settings,
            fidelity_mode=module_fidelity_mode(),
        )
        processed_path = result.comparison_artifacts.get("processed")
        if processed_path:
            self.media_player.setSource(QUrl.fromLocalFile(processed_path))
            self.media_player.play()
            self.preview_status.setText(f"Loaded processed preview clip: {processed_path}")
        else:
            self.preview_status.setText("Preview metadata was created, but no processed clip was available to play.")
        self.output.setPlainText(json.dumps(result.to_dict(), indent=2, sort_keys=True))


def module_comparison_mode():
    from upskayledd.models import ComparisonMode

    return ComparisonMode.SLIDER_WIPE


def module_fidelity_mode():
    from upskayledd.models import FidelityMode

    return FidelityMode.EXACT


def main() -> int:
    app = QApplication(sys.argv)
    window = SpikeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
