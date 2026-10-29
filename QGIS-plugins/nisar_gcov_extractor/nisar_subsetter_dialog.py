import os
import webbrowser
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog
)
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtCore import Qt
from qgis.gui import QgisInterface, QgsExtentGroupBox, QgsMapToolExtent
from qgis.core import QgsRectangle


class NisarSubsetterDialog(QDialog):
    """Dialog for capturing NISAR URL, bounding box, output dir, and Earthdata Token."""

    def __init__(self, iface: QgisInterface, parent=None):
        parent_widget = parent or (iface.mainWindow() if iface else None)
        super().__init__(parent_widget)

        self.iface = iface
        self.map_tool = None
        self.previous_map_tool = None

        self.setWindowTitle("NISAR GCOV Frequency A Extractor")
        self.resize(520, 380)

        layout = QVBoxLayout()

        # --- Top Header Layout with Left Icon and Right Logo ---
        header_layout = QHBoxLayout()

        # 1. Left Icon
        self.icon_label = QLabel()
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon_pixmap = QPixmap(icon_path)

        if not icon_pixmap.isNull():
            scaled_icon = icon_pixmap.scaledToHeight(32, Qt.TransformationMode.SmoothTransformation)
            self.icon_label.setPixmap(scaled_icon)
            header_layout.addWidget(self.icon_label)

        # 2. Header Title / Description
        header_label = QLabel("<h2>NISAR GCOV Extractor</h2>")
        header_layout.addWidget(header_label)

        # Flexible spacer to push the right logo to the far right
        header_layout.addStretch()

        # 3. Right Logo
        self.logo_label = QLabel()
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        logo_pixmap = QPixmap(logo_path)

        if not logo_pixmap.isNull():
            scaled_logo = logo_pixmap.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation)
            self.logo_label.setPixmap(scaled_logo)
            header_layout.addWidget(self.logo_label)

        layout.addLayout(header_layout)

        # 1. HDF5 Granule URL
        layout.addWidget(QLabel("Earthdata HDF5 Granule URL:"))
        self.txt_url = QLineEdit()
        self.txt_url.setPlaceholderText("Enter download URL (i.e. https://nisar.asf.earthdatacloud.nasa.gov/NISAR/___.h5)")
        layout.addWidget(self.txt_url)

        # 2. Bearer Token Input + Helper Link
        token_label_layout = QHBoxLayout()
        token_label_layout.addWidget(QLabel("Earthdata Bearer Token:"))

        btn_get_token = QPushButton("Generate Token ↗")
        btn_get_token.setStyleSheet("border: none; color: #0066cc; text-align: right;")
        btn_get_token.clicked.connect(self.open_token_page)
        token_label_layout.addWidget(btn_get_token)

        layout.addLayout(token_label_layout)

        self.txt_token = QLineEdit()
        # PyQt6 Scoped Enum Syntax
        self.txt_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_token.setPlaceholderText("Paste token here...")
        layout.addWidget(self.txt_token)

        # 3. Spatial Extent Widget
        self.extent_box = QgsExtentGroupBox()
        self.extent_box.setTitle("Bounding Box Extent")

        if self.iface and self.iface.mapCanvas():
            canvas = self.iface.mapCanvas()
            self.extent_box.setMapCanvas(canvas)
            self.extent_box.setOutputCrs(canvas.mapSettings().destinationCrs())
            self.extent_box.setCurrentExtent(
                canvas.extent(),
                canvas.mapSettings().destinationCrs()
            )

        layout.addWidget(self.extent_box)

        # Draw Extent Canvas Intercept
        btn_draw_canvas = QPushButton("🎯 Draw Extent on Map Canvas")
        btn_draw_canvas.clicked.connect(self.start_interactive_draw)
        layout.addWidget(btn_draw_canvas)

        # 4. Output Directory Picker
        layout.addWidget(QLabel("Output Folder:"))
        dir_layout = QHBoxLayout()
        self.txt_out_dir = QLineEdit()
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self.browse_output_dir)
        dir_layout.addWidget(self.txt_out_dir)
        dir_layout.addWidget(btn_browse)
        layout.addLayout(dir_layout)

        # 5. Dialog Action Buttons
        action_layout = QHBoxLayout()
        self.btn_run = QPushButton("Extract & Load")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_run.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        action_layout.addWidget(self.btn_run)
        action_layout.addWidget(self.btn_cancel)
        layout.addLayout(action_layout)

        self.setLayout(layout)

    def start_interactive_draw(self):
        canvas = self.iface.mapCanvas()
        if not canvas:
            return

        self.previous_map_tool = canvas.mapTool()
        self.map_tool = QgsMapToolExtent(canvas)
        self.map_tool.extentChanged.connect(self.on_canvas_extent_selected)

        self.hide()
        canvas.setMapTool(self.map_tool)

    def on_canvas_extent_selected(self, extent: QgsRectangle):
        canvas = self.iface.mapCanvas()

        if self.previous_map_tool:
            canvas.setMapTool(self.previous_map_tool)

        crs = canvas.mapSettings().destinationCrs()
        self.extent_box.setCurrentExtent(extent, crs)

        self.show()
        self.raise_()
        self.activateWindow()

    def open_token_page(self):
        webbrowser.open("https://urs.earthdata.nasa.gov/documentation/for_users/user_token")

    def browse_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder:
            self.txt_out_dir.setText(folder)

    def get_inputs(self):
        extent = self.extent_box.outputExtent()

        bbox_coords = [
            extent.xMinimum(),
            extent.yMinimum(),
            extent.xMaximum(),
            extent.yMaximum()
        ] if extent and not extent.isEmpty() else None

        return {
            "url": self.txt_url.text().strip(),
            "token": self.txt_token.text().strip(),
            "bbox": bbox_coords,
            "out_dir": self.txt_out_dir.text().strip()
        }