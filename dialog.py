from qgis.core import (
    QgsApplication,
    QgsProject,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from .config import load_config
from .decoder import itv_parser
from .map_tool import FeaturePickerTool
from .processing import ExportTask, ProcessingTask


def _get_iface():
    """Return the QGIS iface object from the global scope."""
    from qgis.utils import iface

    return iface


def _layer_from_config(layer_id):
    """Return a QgsVectorLayer from the project by id, or None."""
    if not layer_id:
        return None
    return QgsProject.instance().mapLayer(layer_id)


class XmlReaderDialog(QDialog):
    """
    Import dialog.
    Layer/field configuration is read from config.json (set via Settings menu).
    No layer combos here any more.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importer XML NF EN 13508-2")
        self.resize(420, 320)
        self._cfg = load_config()
        self.current_task = None
        layout = QVBoxLayout()
        file_layout = QHBoxLayout()
        self.label = QLabel("Fichier XML / TXT :")
        self.line_edit = QLineEdit()
        self.line_edit.setReadOnly(True)
        self.btn_browse = QPushButton("Parcourir")
        file_layout.addWidget(self.label)
        file_layout.addWidget(self.line_edit)
        file_layout.addWidget(self.btn_browse)
        self.config_label = QLabel()
        self.config_label.setWordWrap(True)
        self._refresh_config_label()
        self.btn_process = QPushButton("Traiter")
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addLayout(file_layout)
        layout.addWidget(self.config_label)
        layout.addWidget(self.btn_process)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)
        self.btn_browse.clicked.connect(self.browse_file)
        self.btn_process.clicked.connect(self.process_all)

    def _refresh_config_label(self):
        cfg = self._cfg
        troncon_layer = _layer_from_config(cfg.get("troncon_layer_id", ""))
        branch_layer = _layer_from_config(cfg.get("branchement_layer_id", ""))
        t_name = troncon_layer.name() if troncon_layer else "⚠ non configuré"
        b_name = branch_layer.name() if branch_layer else "⚠ non configuré"
        t_field = cfg.get("troncon_field", "⚠ non configuré")
        b_field = cfg.get("branchement_field", "⚠ non configuré")
        self.config_label.setText(
            f"<small>"
            f"Tronçon : <b>{t_name}</b> · champ <b>{t_field}</b><br>"
            f"Branchement : <b>{b_name}</b> · champ <b>{b_field}</b><br>"
            f"<i>(modifier via Extensions → QITV → Paramètres)</i>"
            f"</small>"
        )

    def browse_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Ouvrir un fichier XML ou TXT",
            "",
            "Fichiers XML ou TXT (*.xml *.txt);;Tous les fichiers (*)",
        )
        if filename:
            self.line_edit.setText(filename)

    def process_all(self):
        if self.current_task is not None:
            return

        # Reload config each time in case settings changed
        self._cfg = load_config()
        self._refresh_config_label()

        filename = self.line_edit.text()
        if not filename:
            self.text_edit.setPlainText("Aucun fichier sélectionné.")
            return

        layer_id = self._cfg.get("troncon_layer_id", "")
        selected_field = self._cfg.get("troncon_field", "")
        branchement_layer_id = self._cfg.get("branchement_layer_id", "")
        branchement_selected_field = self._cfg.get("branchement_field", "")

        if not layer_id or not selected_field:
            self.text_edit.setPlainText(
                "Couche tronçon non configurée.\n"
                "Allez dans Extensions → QITV → Paramètres."
            )
            return

        if not branchement_layer_id or not branchement_selected_field:
            self.text_edit.setPlainText(
                "Couche branchement non configurée.\n"
                "Allez dans Extensions → QITV → Paramètres."
            )
            return

        try:
            content = itv_parser(filename)
        except Exception as e:
            self.text_edit.setPlainText(f"Erreur de lecture du fichier :\n{e}")
            return

        self.btn_process.setEnabled(False)
        self.text_edit.setPlainText("Traitement… Veuillez patienter.")

        self.current_task = ProcessingTask(
            "Traitement du fichier XML",
            filename,
            content,
            layer_id,
            selected_field,
            branchement_layer_id,
            branchement_selected_field,
        )
        self.current_task.taskCompleted.connect(self.task_finished)
        QgsApplication.taskManager().addTask(self.current_task)

    def task_finished(self):
        self.btn_process.setEnabled(True)
        if self.current_task.error:
            self.text_edit.setPlainText(
                f"Erreur lors du traitement :\n{self.current_task.error}"
            )
        else:
            self.text_edit.setPlainText(self.current_task.result_text)
        self.current_task = None


_SENS_OPTIONS = [
    ("A", "A – Amont vers aval"),
    ("B", "B – Aval vers amont"),
    ("Z", "Z – Inconnu"),
]
_TYPE_EMPL_OPTIONS = [
    ("A", "A – Public"),
    ("B", "B – Privé"),
    ("Z", "Z – Inconnu"),
]
_METHODE_OPTIONS = [
    ("C", "C – Caméra"),
    ("A", "A – Visuel"),
    ("B", "B – Laser"),
    ("Z", "Z – Autre"),
]
_FORME_OPTIONS = [
    ("AX", "AX – Autre / Inconnu"),
    ("AA", "AA – Circulaire"),
    ("AB", "AB – Ovoïde"),
    ("AC", "AC – Rectangulaire"),
    ("AD", "AD – Trapézoïdal"),
    ("AE", "AE – Elliptique"),
    ("AH", "AH – Brique"),
    ("Z", "Z  – Inconnu"),
]
_ACA_OPTIONS = [
    ("A", "A – Simple"),
    ("B", "B – Double"),
    ("Z", "Z – Inconnu"),
]
_ACK_OPTIONS = [
    ("A", "A – Bon"),
    ("B", "B – Acceptable"),
    ("C", "C – Mauvais"),
    ("Z", "Z – Inconnu"),
]


def _make_combo(options, default_code=None):
    combo = QComboBox()
    for code, label in options:
        combo.addItem(label, code)
    if default_code:
        for i in range(combo.count()):
            if combo.itemData(i) == default_code:
                combo.setCurrentIndex(i)
                break
    return combo


def _set_combo(combo, code):
    for i in range(combo.count()):
        if combo.itemData(i) == code:
            combo.setCurrentIndex(i)
            return


class TubeDialog(QDialog):
    """
    Sub-dialog: create or edit a single tube (one ZB block).
    The 📍 button next to AAA activates a single-pick map tool that fills
    the AAA field from the configured tronçon layer.
    """

    tube_validated = pyqtSignal(dict, int)

    def __init__(self, parent=None, existing=None, edit_index=-1):
        super().__init__(parent)
        self.setWindowTitle("Tube" if existing is None else "Modifier le tube")
        self.resize(440, 500)
        self._data = None
        self._pick_tool = None
        self._edit_index = edit_index

        layout = QVBoxLayout()
        grp_id = QGroupBox("Identification")
        form_id = QFormLayout()
        aaa_row = QHBoxLayout()
        self.aaa = QLineEdit()
        self.aaa.setPlaceholderText("ex: RV20112-RV20160")
        self.btn_pick = QPushButton()
        self.btn_pick.setIcon(QIcon(":/plugins/QITV/picker.svg"))
        self.btn_pick.setToolTip(
            "Cliquer sur un tronçon dans la carte pour remplir ce champ"
        )
        self.btn_pick.setFixedWidth(32)
        aaa_row.addWidget(self.aaa)
        aaa_row.addWidget(self.btn_pick)
        self.aab = QLineEdit()
        self.aab.setPlaceholderText("ex: RV20112-1")
        self.aad = QLineEdit()
        self.aad.setPlaceholderText("= AAB si vide")
        self.aaf = QLineEdit()
        self.aaf.setPlaceholderText("ex: RV20160-2")
        self.aaj = QLineEdit()
        self.aaj.setPlaceholderText("ex: ROUTE D'ITTENHEIM")
        self.aan = QLineEdit()
        self.aan.setPlaceholderText("ex: ACHENHEIM")
        self.aak = _make_combo(_SENS_OPTIONS, "B")
        self.aal = _make_combo(_TYPE_EMPL_OPTIONS, "A")
        self.aav = QCheckBox()
        form_id.addRow("Numéro tronçon (AAA)* :", aaa_row)
        form_id.addRow("Nœud départ (AAB)* :", self.aab)
        form_id.addRow("Nœud départ réf. (AAD) :", self.aad)
        form_id.addRow("Nœud arrivée (AAF)* :", self.aaf)
        form_id.addRow("Rue (AAJ) :", self.aaj)
        form_id.addRow("Commune (AAN) :", self.aan)
        form_id.addRow("Sens écoulement (AAK) :", self.aak)
        form_id.addRow("Type emplacement (AAL) :", self.aal)
        form_id.addRow("Branchement :", self.aav)
        grp_id.setLayout(form_id)
        grp_car = QGroupBox("Caractéristiques du tube")
        form_car = QFormLayout()
        self.abp = _make_combo(_METHODE_OPTIONS, "C")
        self.aca = _make_combo(_ACA_OPTIONS, "Z")
        self.acb = QSpinBox()
        self.acb.setRange(0, 9999)
        self.acb.setSuffix(" mm")
        self.acc = QSpinBox()
        self.acc.setRange(0, 9999)
        self.acc.setSuffix(" mm")
        self.acc.setSpecialValueText("= Hauteur")
        self.acd = _make_combo(_FORME_OPTIONS, "AX")
        self.ack = _make_combo(_ACK_OPTIONS, "Z")
        form_car.addRow("Méthode inspection (ABP) :", self.abp)
        form_car.addRow("Type conduite (ACA) :", self.aca)
        form_car.addRow("Hauteur / Ø (ACB) :", self.acb)
        form_car.addRow("Largeur (ACC) :", self.acc)
        form_car.addRow("Forme section (ACD) :", self.acd)
        form_car.addRow("État général (ACK) :", self.ack)
        grp_car.setLayout(form_car)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #b05000; font-style: italic;")
        btn_row = QHBoxLayout()
        self.btn_ok = QPushButton("Valider")
        self.btn_cancel = QPushButton("Annuler")
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(self.btn_cancel)
        layout.addWidget(grp_id)
        layout.addWidget(grp_car)
        layout.addWidget(self.status_label)
        layout.addLayout(btn_row)
        self.setLayout(layout)
        self.btn_ok.clicked.connect(self._on_ok)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_pick.clicked.connect(self._start_map_pick)
        if existing:
            self._prefill(existing)

    def _start_map_pick(self):
        """Activate the FeaturePickerTool on the configured tronçon layer."""
        cfg = load_config()
        layer = _layer_from_config(cfg.get("troncon_layer_id", ""))
        field = cfg.get("troncon_field", "")
        if not layer or not field:
            QMessageBox.warning(
                self,
                "Couche non configurée",
                "Configurez la couche tronçon dans Extensions → QITV → Paramètres.",
            )
            return
        iface = _get_iface()
        canvas = iface.mapCanvas()
        self.status_label.setText(
            "Cliquez sur un tronçon dans la carte… (Échap pour annuler)"
        )
        self.btn_pick.setEnabled(False)
        self.setWindowModality(Qt.NonModal)
        self._pick_tool = FeaturePickerTool(canvas, layer, field)
        self._pick_tool.feature_picked.connect(self._on_feature_picked)
        canvas.setMapTool(self._pick_tool)

    def _on_feature_picked(self, value):
        """Called by FeaturePickerTool after a single click."""
        self.setWindowModality(Qt.ApplicationModal)
        self.activateWindow()
        self.btn_pick.setEnabled(True)
        self.status_label.setText("")
        self._pick_tool = None
        if value:
            self.aaa.setText(value)
        else:
            self.status_label.setText("Aucun tronçon trouvé à cet emplacement.")

    def _restore_tool(self):
        """Cancel any active pick tool cleanly."""
        if self._pick_tool is not None:
            iface = _get_iface()
            canvas = iface.mapCanvas()
            canvas.unsetMapTool(self._pick_tool)
            self._pick_tool = None
            self.setWindowModality(Qt.ApplicationModal)

    def _on_cancel(self):
        self._restore_tool()
        self.reject()
        self.close()

    def closeEvent(self, event):
        self._restore_tool()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self._pick_tool is not None:
                self._restore_tool()
                self.activateWindow()
                self.status_label.setText("")
                self.btn_pick.setEnabled(True)
            else:
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def _prefill(self, d):
        self.aaa.setText(d.get("AAA", ""))
        self.aab.setText(d.get("AAB", ""))
        self.aad.setText(d.get("AAD", ""))
        self.aaf.setText(d.get("AAF", ""))
        self.aaj.setText(d.get("AAJ", ""))
        self.aan.setText(d.get("AAN", ""))
        _set_combo(self.aak, d.get("AAK", "B"))
        _set_combo(self.aal, d.get("AAL", "A"))
        _set_combo(self.abp, d.get("ABP", "C"))
        _set_combo(self.aca, d.get("ACA", "Z"))
        _set_combo(self.acd, d.get("ACD", "AX"))
        _set_combo(self.ack, d.get("ACK", "Z"))
        try:
            self.acb.setValue(int(d.get("ACB", 0)))
        except (ValueError, TypeError):
            self.acb.setValue(0)
        try:
            self.acc.setValue(int(d.get("ACC", 0)))
        except (ValueError, TypeError):
            self.acc.setValue(0)

    def _on_ok(self):
        aaa = self.aaa.text().strip()
        aab = self.aab.text().strip()
        aaf = self.aaf.text().strip()
        if not aaa or not aab or not aaf:
            QMessageBox.warning(
                self,
                "Champs obligatoires",
                "AAA (tronçon), AAB (nœud départ) et AAF (nœud arrivée) "
                "sont obligatoires.",
            )
            return
        acb = self.acb.value()
        acc = self.acc.value() if self.acc.value() > 0 else acb
        self._data = {
            "AAA": aaa,
            "AAB": aab,
            "AAD": self.aad.text().strip() or aab,
            "AAF": aaf,
            "AAJ": self.aaj.text().strip(),
            "AAN": self.aan.text().strip(),
            "AAK": self.aak.currentData(),
            "AAL": self.aal.currentData(),
            "ABP": self.abp.currentData(),
            "ACA": self.aca.currentData(),
            "ACB": str(acb),
            "ACC": str(acc),
            "ACD": self.acd.currentData(),
            "ACK": self.ack.currentData(),
            "ADE": "",
            "ACG": "",
            "ACH": "",
            "ACI": "",
        }
        if self.aav.isChecked():
            self._data["AAV"] = ""
        self.tube_validated.emit(self._data, self._edit_index)
        self.close()

    def get_data(self):
        return self._data


class ExportDialog(QDialog):
    """
    Main export dialog.
    User builds a list of tubes via TubeDialog, then exports to TXT + XML.
    Both files are written automatically side-by-side (same base name).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exporter NF EN 13508-2")
        self.resize(560, 500)
        self._tubes = []
        self._current_task = None
        self._active_tube_dialog = None
        layout = QVBoxLayout()
        grp_list = QGroupBox("Interventions à exporter")
        list_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        list_layout.addWidget(self.list_widget)
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("➕  Nouvelle intervention")
        self.btn_edit = QPushButton("✏️  Modifier")
        self.btn_delete = QPushButton("🗑️  Supprimer")
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete)
        list_layout.addLayout(btn_row)
        grp_list.setLayout(list_layout)
        grp_out = QGroupBox("Fichier de sortie  (TXT + XML générés automatiquement)")
        out_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText(
            "Choisir l'emplacement des fichiers .txt/.xml …"
        )
        self.btn_browse = QPushButton("Parcourir…")
        out_layout.addWidget(self.path_edit)
        out_layout.addWidget(self.btn_browse)
        grp_out.setLayout(out_layout)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        bottom_row = QHBoxLayout()
        self.btn_export = QPushButton("Exporter TXT + XML")
        self.btn_close = QPushButton("Fermer")
        bottom_row.addWidget(self.btn_export)
        bottom_row.addWidget(self.btn_close)
        layout.addWidget(grp_list)
        layout.addWidget(grp_out)
        layout.addWidget(self.log)
        layout.addLayout(bottom_row)
        self.setLayout(layout)
        self.btn_add.clicked.connect(self._add_tube)
        self.btn_edit.clicked.connect(self._edit_tube)
        self.btn_delete.clicked.connect(self._delete_tube)
        self.btn_browse.clicked.connect(self._browse_output)
        self.btn_export.clicked.connect(self._export)
        self.btn_close.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(self._edit_tube)

    def _label(self, d):
        parts = [d.get("AAA", "?")]
        acb = d.get("ACB", "")
        if acb and acb != "0":
            parts.append(f"Ø{acb} mm")
        acd = d.get("ACD", "")
        if acd:
            parts.append(acd)
        return "  |  ".join(parts)

    def _refresh_list(self):
        self.list_widget.clear()
        for d in self._tubes:
            self.list_widget.addItem(QListWidgetItem(self._label(d)))

    def _log(self, msg):
        self.log.append(msg)

    def _add_tube(self):
        if self._active_tube_dialog is not None:
            self._active_tube_dialog.close()
            self._active_tube_dialog.deleteLater()
        dlg = TubeDialog(self, existing=None, edit_index=-1)
        dlg.tube_validated.connect(self._on_tube_validated)
        dlg.show()
        self._active_tube_dialog = dlg

    def _edit_tube(self):
        row = self.list_widget.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Sélection", "Sélectionnez une intervention à modifier."
            )
            return
        if self._active_tube_dialog is not None:
            self._active_tube_dialog.close()
            self._active_tube_dialog.deleteLater()
        dlg = TubeDialog(self, existing=self._tubes[row], edit_index=row)
        dlg.tube_validated.connect(self._on_tube_validated)
        dlg.show()
        self._active_tube_dialog = dlg

    def _on_tube_validated(self, data, edit_index):
        """Slot called when intervention validated in TubeDialog."""
        if edit_index == -1:
            self._tubes.append(data)
            self._log(f"Intervention ajoutée : {data['AAA']}")
        else:
            self._tubes[edit_index] = data
            self._log(f"intervention modifiée : {data['AAA']}")
        self._refresh_list()
        if self._active_tube_dialog is not None:
            self._active_tube_dialog.deleteLater()
            self._active_tube_dialog = None

    def _delete_tube(self):
        row = self.list_widget.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Sélection", "Sélectionnez une intervention à supprimer."
            )
            return
        aaa = self._tubes[row].get("AAA", "")
        if (
            QMessageBox.question(
                self,
                "Confirmer",
                f"Supprimer l'intervention « {aaa} » ?",
                QMessageBox.Yes | QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self._tubes.pop(row)
            self._refresh_list()
            self._log(f"intervention supprimée : {aaa}")

    def _browse_output(self):
        """
        Ask the user to choose a .txt destination.
        The matching .xml file will be written automatically alongside it.
        """
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer le fichier TXT (le XML sera créé au même endroit)",
            "",
            "Fichiers TXT (*.txt);;Tous les fichiers (*)",
        )
        if path:
            if not path.lower().endswith(".txt"):
                path += ".txt"
            self.path_edit.setText(path)
            xml_preview = (
                path[:-4] + ".xml" if path.lower().endswith(".txt") else path + ".xml"
            )
            self._log(f"Destination TXT : {path}")
            self._log(f"Destination XML : {xml_preview}  (généré automatiquement)")

    def _export(self):
        if self._current_task is not None:
            return
        if not self._tubes:
            QMessageBox.warning(
                self, "Aucune intervention", "Ajoutez au moins une intervention."
            )
            return
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(
                self, "Fichier manquant", "Choisissez un fichier de sortie."
            )
            return
        self.btn_export.setEnabled(False)
        self._log("Export en cours…")
        self._current_task = ExportTask("Export NF EN 13508-2", self._tubes, path)
        self._current_task.taskCompleted.connect(self._export_finished)
        QgsApplication.taskManager().addTask(self._current_task)

    def _export_finished(self):
        self.btn_export.setEnabled(True)
        if self._current_task.error:
            self._log(f"❌ Erreur : {self._current_task.error}")
            QMessageBox.critical(
                self, "Erreur", f"Erreur lors de l'export :\n{self._current_task.error}"
            )
        else:
            self._log(f"✅ {self._current_task.result_text}")
            QMessageBox.information(
                self, "Export réussi", self._current_task.result_text
            )
        self._current_task = None
