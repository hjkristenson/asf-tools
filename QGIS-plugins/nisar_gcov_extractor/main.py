import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QMenu
from qgis.core import Qgis, QgsApplication
from .nisar_subsetter_dialog import NisarSubsetterDialog
from .nisar_subset_downloader import NisarSubsetTask


class NisarSubsetterPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dialog = None
        self.action = None
        self.custom_menu = None

    def initGui(self):
        """Creates the action and adds it to a custom top-level menu and toolbar."""
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

        self.action = QAction(
            icon,
            "NISAR GCOV Frequency A Extractor",
            self.iface.mainWindow()
        )
        self.action.setStatusTip(
            "Stream and subset NISAR Frequency A diagonal term covariance datasets from GCOV HDF5 data hosted in Earthdata Cloud")
        self.action.triggered.connect(self.run_extractor)

        # 1. Create top-level menu on the QGIS Menu Bar
        menu_bar = self.iface.mainWindow().menuBar()
        self.custom_menu = QMenu("NISAR Tools", menu_bar)

        # Add the menu to the menu bar before the "Help" menu (or at the end)
        menu_bar.insertMenu(self.iface.firstRightStandardMenu().menuAction(), self.custom_menu)

        # 2. Add the action to your custom menu
        self.custom_menu.addAction(self.action)

        # 3. Add to the toolbar
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        """Removes the action and custom menu from QGIS UI when plugin is disabled or reloaded."""
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            del self.action

        if self.custom_menu:
            # Remove custom menu from menu bar
            self.iface.mainWindow().menuBar().removeAction(self.custom_menu.menuAction())
            del self.custom_menu

    def run_extractor(self):
        """Launches the dialog non-modally so interactive canvas selection tools work."""
        self.dialog = NisarSubsetterDialog(self.iface)
        self.dialog.setWindowModality(Qt.WindowModality.NonModal)

        def on_accept():
            inputs = self.dialog.get_inputs()

            if not inputs["url"] or not inputs["token"] or not inputs["bbox"] or not inputs["out_dir"]:
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "Missing Information",
                    "Please fill in all required fields."
                )
                return

            task = NisarSubsetTask(
                description="Extracting NISAR GCOV Frequency A Layers",
                h5_https_url=inputs["url"],
                bbox_target_crs=inputs["bbox"],
                output_dir=inputs["out_dir"],
                bearer_token=inputs["token"]
            )

            QgsApplication.taskManager().addTask(task)

            self.iface.messageBar().pushMessage(
                "NISAR GCOV Extractor",
                "Extraction started in the background.",
                level=Qgis.Info,
                duration=4
            )

        self.dialog.accepted.connect(on_accept)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
