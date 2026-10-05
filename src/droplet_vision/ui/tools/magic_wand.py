"""Temporary raw-mask interaction; confirmed polygons use normal history commands."""
from ..i18n import tr
from copy import deepcopy
import numpy as np
from PySide6.QtGui import QImage, QPixmap
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

    def activate(self, canvas):
        super().activate(canvas)
        self.editor.wand_dock.show()
        self.editor.message(tr('Click a target region to select similar grayscale pixels.'))

    def mouse_press(self, position):
        if not self.editor.can_draw('polygon') or not supported_image(self.editor.window.raw_image):
            self.editor.message(tr('Current image does not support Magic Wand.'))
            return
        image = self.editor.window.raw_image
        self.base = np.zeros(image.shape, dtype=bool) if self.mask is None else self.mask.copy()
        self.base_operations = deepcopy(self.operations)
        self.seed = [int(round(position[0])), int(round(position[1]))]
        self.operation = self.editor.wand_panel.mode.currentData()
        self.recalculate()

    def recalculate(self):
        if self.seed is None:
            return
        panel = self.editor.wand_panel
        try:
            region, reference = grow_region(self.editor.window.raw_image, self.seed,
                                            panel.tolerance.value(), panel.connectivity.currentData(), panel.config)
            mask = combine_selection(self.base, region, self.operation, panel.config.max_region_fraction)
        except ValueError as error:
            self.valid = False
            self.editor.clear_preview()
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
        self.editor.clear_preview()
        rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
        rgba[mask] = [50, 210, 255, 110]
        qimage = QImage(rgba.data, mask.shape[1], mask.shape[0], rgba.strides[0], QImage.Format.Format_RGBA8888).copy()
        item = self.editor.canvas.scene().addPixmap(QPixmap.fromImage(qimage))
        item.setZValue(24)
        self.editor.preview.append(item)
        self.editor.message(tr('Adjust tolerance to change the selection. Confirm creates manual polygons.'))

    def commit(self):
        if not self.valid or self.mask is None:
            return False
        panel = self.editor.wand_panel
        try:
            polygons = mask_to_polygons(self.mask, panel.config.polygon_simplification_tolerance_px)
        except ValueError as error:
            self.editor.message(str(error))
            return False
        latest = self.operations[-1]
        attributes = {'creation_tool':'magic_wand', 'magic_wand_preset_id':panel.config.preset_id,
                      'magic_wand_tolerance':latest['tolerance'],
                      'magic_wand_connectivity':latest['connectivity'],
                      'magic_wand_seed_reference':latest['seed_reference'],
                      'magic_wand_operations':deepcopy(self.operations),
                      'magic_wand_max_region_fraction':panel.config.max_region_fraction,
                      'magic_wand_simplification_tolerance_px':panel.config.polygon_simplification_tolerance_px}
        if self.editor.create_polygon_batch(polygons, attributes):
            self.cancel()
            self.editor.switch_tool('select')
            return True
        return False

    def cancel(self):
        self.mask = self.base = self.seed = None
        self.operations = []
        self.base_operations = []
        self.valid = False
        self.editor.wand_panel.confirm_button.setEnabled(False)
        super().cancel()
