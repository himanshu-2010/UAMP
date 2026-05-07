"""
UAMP - Graphical User Interface
A professional media player with ASCII/Braille rendering.
"""

import sys
import time
import numpy as np
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QSlider, QLabel, 
                             QFileDialog, QComboBox, QCheckBox, QGroupBox,
                             QScrollArea, QFrame, QSplitter, QInputDialog, QMessageBox,
                             QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QSize, QRectF
from PySide6.QtGui import QImage, QPixmap, QFont, QAction, QPalette, QColor, QPainter

from uamp.media_engine import MediaEngine, ASCII_SETS, is_url
from uamp.settings import AppSettings
from uamp.fsal import MEDIA_EXTS

class VideoWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: black;")
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def display_frame(self, frame_data, settings, is_ascii=False):
        if frame_data is None or len(frame_data) == 0: return
        
        if not is_ascii:
            # frame_data is RGB numpy array
            h, w, ch = frame_data.shape
            bytes_per_line = ch * w
            qimg = QImage(frame_data.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            self.setPixmap(pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            # Render ASCII/Braille with colors in GUI
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.GlobalColor.black)
            painter = QPainter(pixmap)
            
            rows = len(frame_data)
            cols = len(frame_data[0]) if rows > 0 else 0
            if cols == 0: return

            # Dynamic font size based on density
            font_size = max(1, int(self.height() / rows))
            font = QFont("Monospace", font_size)
            font.setStyleHint(QFont.StyleHint.Monospace)
            painter.setFont(font)
            
            char_w = self.width() / cols
            char_h = self.height() / rows
            
            for row_i, line in enumerate(frame_data):
                for col_i, (char, color_tuple) in enumerate(line):
                    if settings.color_mode and color_tuple:
                        painter.setPen(QColor(*color_tuple))
                    else:
                        painter.setPen(Qt.GlobalColor.green)
                    
                    rect = QRectF(col_i * char_w, row_i * char_h, char_w, char_h)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, char)
            
            painter.end()
            self.setPixmap(pixmap)

class UAMPGui(QMainWindow):
    def __init__(self, start_path=None):
        super().__init__()
        self.setWindowTitle("UAMP - Universal ASCII Media Player")
        self.resize(1200, 800)
        
        self.settings = AppSettings()
        self.engine = None
        self.cur_idx = 0
        self.playing = False
        self.ascii_mode = False
        
        self._init_ui()
        self._init_menu()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_frame)
        
        if start_path:
            self._load_file(start_path)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Left Side: Video & Controls
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        
        self.video_widget = VideoWidget()
        left_layout.addWidget(self.video_widget)
        
        # Control Bar
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(40, 40)
        self.play_btn.clicked.connect(self._toggle_play)
        controls_layout.addWidget(self.play_btn)
        
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.sliderMoved.connect(self._seek)
        controls_layout.addWidget(self.seek_slider)
        
        self.time_label = QLabel("00:00 / 00:00")
        controls_layout.addWidget(self.time_label)
        
        left_layout.addWidget(controls)
        
        # Right Side: Settings
        settings_panel = QScrollArea()
        settings_panel.setWidgetResizable(True)
        settings_panel.setFixedWidth(280)
        
        settings_content = QWidget()
        settings_layout = QVBoxLayout(settings_content)
        
        # Mode Group
        mode_group = QGroupBox("Playback Mode")
        mode_vbox = QVBoxLayout()
        self.ascii_check = QCheckBox("Enable ASCII Mode")
        self.ascii_check.stateChanged.connect(self._toggle_ascii)
        mode_vbox.addWidget(self.ascii_check)
        self.braille_check = QCheckBox("Braille Mode")
        self.braille_check.stateChanged.connect(self._toggle_braille)
        mode_vbox.addWidget(self.braille_check)
        self.color_check = QCheckBox("Color Mode")
        self.color_check.stateChanged.connect(self._toggle_color)
        mode_vbox.addWidget(self.color_check)
        self.loop_check = QCheckBox("Loop Media")
        self.loop_check.setChecked(self.settings.loop)
        self.loop_check.stateChanged.connect(self._toggle_loop)
        mode_vbox.addWidget(self.loop_check)
        mode_group.setLayout(mode_vbox)
        settings_layout.addWidget(mode_group)
        
        # Rendering Group
        render_group = QGroupBox("ASCII Rendering")
        render_vbox = QVBoxLayout()
        
        render_vbox.addWidget(QLabel("Charset:"))
        self.charset_combo = QComboBox()
        self.charset_combo.addItems(list(ASCII_SETS.keys()))
        self.charset_combo.setCurrentText(self.settings.charset_key)
        self.charset_combo.currentTextChanged.connect(self._change_charset)
        render_vbox.addWidget(self.charset_combo)
        
        render_vbox.addWidget(QLabel("Density:"))
        self.density_combo = QComboBox()
        self.density_combo.addItems(["Standard (1x)", "High (2x)", "Ultra (3x)"])
        self.density_combo.currentIndexChanged.connect(self._change_density)
        render_vbox.addWidget(self.density_combo)
        
        render_vbox.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 100) # 1.0x to 10.0x
        self.zoom_slider.setValue(10)
        self.zoom_slider.valueChanged.connect(self._change_zoom)
        render_vbox.addWidget(self.zoom_slider)
        
        render_group.setLayout(render_vbox)
        settings_layout.addWidget(render_group)
        
        # URL Action Group
        url_group = QGroupBox("Actions")
        url_vbox = QVBoxLayout()
        url_btn = QPushButton("Open URL")
        url_btn.clicked.connect(self._open_url_dialog)
        url_vbox.addWidget(url_btn)
        dl_btn = QPushButton("Download Media")
        dl_btn.clicked.connect(self._download_media)
        url_vbox.addWidget(dl_btn)
        url_group.setLayout(url_vbox)
        settings_layout.addWidget(url_group)
        
        settings_layout.addStretch()
        settings_panel.setWidget(settings_content)
        
        main_layout.addWidget(left_container, 7)
        main_layout.addWidget(settings_panel, 3)

    def _init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        
        open_action = QAction("&Open File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file_dialog)
        file_menu.addAction(open_action)
        
        url_action = QAction("Open &URL...", self)
        url_action.setShortcut("Ctrl+U")
        url_action.triggered.connect(self._open_url_dialog)
        file_menu.addAction(url_action)
        
        file_menu.addSeparator()
        exit_action = QAction("&Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Media", "", "Media Files (*.mp4 *.mkv *.avi *.gif *.jpg *.png *.webp)")
        if path:
            self._load_file(path)

    def _open_url_dialog(self):
        url, ok = QInputDialog.getText(self, "Open URL", "Enter media URL (YouTube, direct link, etc.):")
        if ok and url:
            self._load_file(url)

    def _download_media(self):
        if not self.engine: return
        url = self.engine.filepath
        path, _ = QFileDialog.getSaveFileName(self, "Save Media", "video.mp4")
        if path:
            QMessageBox.information(self, "Download", f"Downloading {url} to {path}...\n(Check terminal for progress)")
            # Use yt-dlp to download
            subprocess.Popen(['yt-dlp', '-o', path, url])

    def _load_file(self, path: str):
        if self.engine: self.engine.stop()
        # Adjusted resolution for GUI ASCII rendering
        self.engine = MediaEngine(path, 120, 60, self.settings)
        self.engine.start()
        self.playing = True
        self.play_btn.setText("⏸")
        self.timer.start(int(1000 / self.settings.fps))
        self.cur_idx = 0

    def _toggle_play(self):
        self.playing = not self.playing
        self.play_btn.setText("▶" if not self.playing else "⏸")
        if self.playing: self.timer.start()
        else: self.timer.stop()

    def _seek(self, value):
        if self.engine:
            path = self.engine.filepath
            self.engine.stop()
            self.engine = MediaEngine(path, 120, 60, self.settings)
            self.engine.start(float(value))
            self.cur_idx = 0

    def _seek_relative(self, seconds):
        if not self.engine: return
        cur_time = (self.cur_idx / self.settings.fps) + self.engine.seek_time
        new_time = max(0, min(self.engine.duration, cur_time + seconds))
        self._seek(new_time)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right:
            self._seek_relative(15)
        elif event.key() == Qt.Key.Key_Left:
            self._seek_relative(-15)
        elif event.key() == Qt.Key.Key_Space:
            self._toggle_play()
        else:
            super().keyPressEvent(event)

    def _toggle_ascii(self, state):
        self.ascii_mode = (state == Qt.CheckState.Checked.value)
        
    def _toggle_braille(self, state):
        self.settings.braille_mode = (state == Qt.CheckState.Checked.value)
        
    def _toggle_color(self, state):
        self.settings.color_mode = (state == Qt.CheckState.Checked.value)

    def _toggle_loop(self, state):
        self.settings.loop = (state == Qt.CheckState.Checked.value)

    def _change_charset(self, key):
        self.settings.set_charset(key)

    def _change_density(self, index):
        self.settings.density = index + 1

    def _change_zoom(self, value):
        self.settings.zoom = value / 10.0

    def _update_frame(self):
        if not self.engine: return
        
        if not self.engine.frames and self.engine.loaded:
            msg = self.engine.error_msg or "Error: Could not decode media."
            self.video_widget.setText(msg)
            self.video_widget.setStyleSheet("background-color: black; color: red; font-weight: bold; font-size: 20px;")
            return

        if not self.playing: return
        
        cnt = len(self.engine.frames)
        if cnt > 0:
            if self.ascii_mode:
                # Get rendered ASCII (includes color info in frame_data)
                frame = self.engine.get_frame(self.cur_idx, 120, 60)
                self.video_widget.display_frame(frame, self.settings, is_ascii=True)
            else:
                # Get raw RGB
                frame = self.engine.get_raw_frame(self.cur_idx)
                self.video_widget.display_frame(frame, self.settings, is_ascii=False)
            
            if not self.engine.is_static:
                self.cur_idx += 1
            
            # Update slider and time
            curr = (self.cur_idx / self.settings.fps) + self.engine.seek_time
            dur = self.engine.duration
            if dur > 0:
                self.seek_slider.blockSignals(True)
                self.seek_slider.setMaximum(int(dur))
                self.seek_slider.setValue(int(curr))
                self.seek_slider.blockSignals(False)
                self.time_label.setText(f"{int(curr//60):02}:{int(curr%60):02} / {int(dur//60):02}:{int(dur%60):02}")
            else:
                self.time_label.setText(f"{int(curr//60):02}:{int(curr%60):02} / Live")

    def closeEvent(self, event):
        if self.engine: self.engine.stop()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Dark Mode Palette
    palette = QPalette()
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(palette)
    
    path = sys.argv[1] if len(sys.argv) > 1 else None
    window = UAMPGui(path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
