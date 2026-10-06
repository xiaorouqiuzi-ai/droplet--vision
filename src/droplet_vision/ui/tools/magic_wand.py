"""Temporary raw-mask interaction; confirmed polygons use normal history commands."""
from ..i18n import tr
from copy import deepcopy
import numpy as np
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QMessageBox
from ...annotations.magic_wand import grow_region, combine_selection, mask_to_polygons, supported_image
from .drawing import EditorTool


class MagicWandTool(EditorTool):
    geometry_type = 'polygon'

    def __init__(self, editor):
        super().__init__(editor)
        self.mask = self.base = self.seed = None
        self.operation = None
        self.operations = []
        self.base_operations = []
        self.valid = False
        from .draft_polygon import DraftPolygonEditor
        self.draft = DraftPolygonEditor(editor)
        self.applied_settings = self.settings()

    def settings(self):
        panel = self.editor.wand_panel
        return (panel.tolerance.value(), panel.connectivity.currentIndex(), panel.mode.currentIndex())

    def allow_reset(self):
        if not self.draft.manual_edited:
            return True
        answer = QMessageBox.question(self.editor.window, tr('Confirm'),
            tr('Recalculating the Magic Wand region will reset manual boundary adjustments. Continue?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            return True
        panel = self.editor.wand_panel
        with QSignalBlocker(panel.tolerance), QSignalBlocker(panel.connectivity), QSignalBlocker(panel.mode):
            panel.tolerance.setValue(self.applied_settings[0])
            panel.connectivity.setCurrentIndex(self.applied_settings[1])
            panel.mode.setCurrentIndex(self.applied_settings[2])
        panel.tolerance_label.setText(tr('Tolerance: ') + str(panel.tolerance.value()))
        return False

    def mode_changed(self):
        if self.allow_reset():
            # Mode config applies to the next seed; current geometry is retained.
            self.applied_settings = self.settings()

    def activate(self, canvas):
        super().activate(canvas)
        self.editor.tool_settings.show_tool("magic_wand")
        self.editor.message(tr('Click a target region to select similar grayscale pixels.'))

    def mouse_press(self, position):
        if self.draft.press(position, add=False):
            return
        if not self.editor.can_draw('polygon') or not supported_image(self.editor.window.raw_image):
            self.editor.message(tr('Current image does not support Magic Wand.'))
            return
        if not self.allow_reset():
            return
        image = self.editor.window.raw_image
        self.base = np.zeros(image.shape, dtype=bool) if self.mask is None else self.mask.copy()
        self.base_operations = deepcopy(self.operations)
        self.seed = [int(round(position[0])), int(round(position[1]))]
        self.operation = self.editor.wand_panel.mode.currentData()
        self.recalculate(approved=True)

    def recalculate(self, approved=False):
        if self.seed is None:
            return
        if not approved and not self.allow_reset():
            return
        panel = self.editor.wand_panel
        try:
            region, reference = grow_region(self.editor.window.raw_image, self.seed,
                                            panel.tolerance.value(), panel.connectivity.currentData(), panel.config)
            mask = combine_selection(self.base, region, self.operation, panel.config.max_region_fraction)
            polygons = mask_to_polygons(mask, panel.config.polygon_simplification_tolerance_px) if mask.any() else []
        except ValueError as error:
            self.valid = False
            self.draft.clear()
            panel.confirm_button.setEnabled(False)
            self.editor.message(str(error))
            return
        self.mask = mask
        entry = {'seed':self.seed[:], 'operation':self.operation,
                 'tolerance':panel.tolerance.value(), 'connectivity':panel.connectivity.currentData(),
                 'seed_reference':reference}
        self.operations = ([] if self.operation == 'replace' else deepcopy(self.base_operations)) + [entry]
        self.valid = bool(mask.any())
        panel.confirm_button.setEnabled(self.valid)
        self.draft.replace(polygons)
        self.applied_settings = self.settings()
        self.editor.message(tr('Closed draft: adjust vertices, then Confirm.'))

    def mouse_move(self, position):
        self.draft.move(position)

    def mouse_release(self, position):
        self.draft.release(position)

    def commit(self):
        if not self.valid or self.mask is None:
            return False
        panel = self.editor.wand_panel
        if not self.draft.closed or not self.draft.active:
            return False
        polygons = deepcopy(self.draft.polygons)
        latest = self.operations[-1]
        attributes = {'creation_tool':'magic_wand', 'magic_wand_preset_id':panel.config.preset_id,
                      'magic_wand_tolerance':latest['tolerance'],
                      'magic_wand_connectivity':latest['connectivity'],
                      'magic_wand_seed_reference':latest['seed_reference'],
                      'magic_wand_operations':deepcopy(self.operations),
                      'magic_wand_max_region_fraction':panel.config.max_region_fraction,
                      'magic_wand_simplification_tolerance_px':panel.config.polygon_simplification_tolerance_px,
                      'magic_wand_boundary_adjusted':self.draft.manual_edited}
        if self.editor.create_polygon_batch(polygons, attributes):
            self.cancel()
            self.editor.switch_tool('select')
            return True
        return False

    def cancel(self):
        self.draft.clear()
        self.mask = self.base = self.seed = None
        self.operations = []
        self.base_operations = []
        self.valid = False
        self.editor.wand_panel.confirm_button.setEnabled(False)
        super().cancel()

    def deactivate(self):
        self.cancel()
        self.draft.dispose()
