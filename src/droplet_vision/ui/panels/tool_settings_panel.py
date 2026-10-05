"""Compact current-tool settings, hosted in the annotation workspace."""
from ..i18n import tr
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton


class ToolSettingsPanel(QWidget):
    HINTS = {
        'select': 'Select an annotation; drag handles to edit. Double-click an edge to insert a vertex.',
        'polygon': 'Click the image to add vertices. Enter finishes; Esc cancels.',
        'magic_wand': 'Click a region in the image, then adjust and confirm the preview.',
        'bbox': 'Press and drag on the image, then release to create a bounding box.',
        'point': 'Click the image to create a point.',
    }

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.pages = {}
        self.current_key = 'select'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        for key in self.HINTS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            self.pages[key] = page
            layout.addWidget(page)
        select_layout = self.pages['select'].layout()
        select_layout.addWidget(editor.window.annotation_panel.details)
        self.vertex_info = QLabel()
        select_layout.addWidget(self.vertex_info)
        self.delete_vertex = QPushButton(tr('Delete Vertex'))
        self.delete_vertex.clicked.connect(editor.delete_vertex)
        select_layout.addWidget(self.delete_vertex)
        polygon_layout = self.pages['polygon'].layout()
        self.vertex_count = QLabel()
        polygon_layout.addWidget(self.vertex_count)
        polygon_layout.addWidget(self._button('Remove last polygon vertex', lambda: editor.tool.backspace()))
        polygon_layout.addWidget(self._button('Edit existing vertices (Select)', lambda: editor.switch_tool('select')))
        polygon_layout.addWidget(QLabel(tr('Insert Vertex: double-click an edge in Select. Delete removes a selected vertex.')))
        polygon_layout.itemAt(polygon_layout.count()-1).widget().setWordWrap(True)
        buttons = QHBoxLayout()
        buttons.addWidget(self._button('Finish (Enter)', lambda: editor.tool.commit()))
        buttons.addWidget(self._button('Cancel (Esc)', editor.cancel))
        polygon_layout.addLayout(buttons)
        self.pages['magic_wand'].layout().addWidget(editor.wand_panel)
        self.show_tool('select')

    @staticmethod
    def _button(text, callback):
        button = QPushButton(tr(text))
        button.clicked.connect(callback)
        return button

    def show_tool(self, key):
        self.current_key = key
        self.hint.setText(tr(self.HINTS[key]))
        for name, page in self.pages.items():
            page.setVisible(name == key)

    def refresh(self):
        editor = self.editor
        self.vertex_count.setText(tr('Current vertices: {count}').format(count=len(getattr(editor.tool, 'points', []))))
        record = editor.selected_record()
        index = editor.selected_vertex
        self.vertex_info.setText(tr('Selected vertex: {index}').format(index=index+1) if index is not None else tr('No vertex selected'))
        self.delete_vertex.setEnabled(bool(record and record.geometry_type == 'polygon' and index is not None and editor.can_edit(record)))
