"""Controls for a Qt-independent, immutable display-settings value."""
from __future__ import annotations
from dataclasses import replace
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QSlider, QDoubleSpinBox, QPushButton)
from ...display import DisplaySettings, display_modes


class DisplayPanel(QWidget):
    changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = DisplaySettings()
        self.previous_enhanced_mode = "manual"
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Display only — raw pixels unchanged"))
        self.mode = QComboBox()
        self.mode.setObjectName("displayMode")
        for key, title in display_modes().items():
            self.mode.addItem(title, key)
        layout.addWidget(self.mode)
        self.manual_controls = QWidget()
        manual_layout = QVBoxLayout(self.manual_controls)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        self.value_labels = {}
        for name, minimum, maximum in (("brightness", -100, 100), ("contrast", 25, 400), ("gamma", 20, 500)):
            label = QLabel()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setObjectName("display" + name.title())
            setattr(self, name, slider)
            self.value_labels[name] = label
            manual_layout.addWidget(label)
            manual_layout.addWidget(slider)
            slider.valueChanged.connect(lambda value, field=name: self.set_settings(
                replace(self.settings, **{field: value / 100})))
        layout.addWidget(self.manual_controls)
        self.auto_controls = QWidget()
        auto_layout = QHBoxLayout(self.auto_controls)
        auto_layout.setContentsMargins(0, 0, 0, 0)
        for name, title in (("percentile_low", "Low"), ("percentile_high", "High")):
            control = QDoubleSpinBox()
            control.setDecimals(1)
            control.setSingleStep(.1)
            control.setRange(0 if name.endswith("low") else .1, 99.9 if name.endswith("low") else 100)
            control.setSuffix("%")
            control.setObjectName(name)
            setattr(self, name, control)
            auto_layout.addWidget(QLabel(title))
            auto_layout.addWidget(control)
            control.valueChanged.connect(lambda value, field=name: self._percentile_changed(field, value))
        layout.addWidget(self.auto_controls)
        self.reset_button = QPushButton("Reset Display")
        self.reset_button.clicked.connect(self.reset)
        layout.addWidget(self.reset_button)
        self.mode.currentIndexChanged.connect(lambda _: self.set_settings(replace(self.settings, mode=self.mode.currentData())))
        self.set_settings(self.settings, emit=False)

    def _percentile_changed(self, field, value):
        values = {field: value}
        if field == "percentile_low" and value >= self.settings.percentile_high:
            values["percentile_high"] = round(value + .1, 1)
        if field == "percentile_high" and value <= self.settings.percentile_low:
            values["percentile_low"] = round(value - .1, 1)
        self.set_settings(replace(self.settings, **values))

    def set_settings(self, settings: DisplaySettings, emit=True):
        index = self.mode.findData(settings.mode)
        if index < 0:
            raise ValueError("Unavailable display mode: " + settings.mode)
        self.settings = settings
        if settings.mode != "raw":
            self.previous_enhanced_mode = settings.mode
        controls = [self.mode, self.brightness, self.contrast, self.gamma, self.percentile_low, self.percentile_high]
        blockers = [QSignalBlocker(control) for control in controls]
        self.mode.setCurrentIndex(index)
        for name in ("brightness", "contrast", "gamma"):
            getattr(self, name).setValue(round(getattr(settings, name) * 100))
        self.percentile_low.setValue(settings.percentile_low)
        self.percentile_high.setValue(settings.percentile_high)
        self.value_labels["brightness"].setText(f"Brightness: {settings.brightness * 100:+.0f}")
        self.value_labels["contrast"].setText(f"Contrast: {settings.contrast:.2f}")
        self.value_labels["gamma"].setText(f"Gamma: {settings.gamma:.2f}")
        self.manual_controls.setEnabled(settings.mode == "manual")
        self.auto_controls.setEnabled(settings.mode == "auto_percentile")
        del blockers
        if emit:
            self.changed.emit(settings)

    def show_raw(self):
        self.set_settings(replace(self.settings, mode="raw"))

    def show_enhanced(self):
        self.set_settings(replace(self.settings, mode=self.previous_enhanced_mode))

    def reset(self):
        self.previous_enhanced_mode = "manual"
        self.set_settings(DisplaySettings())
