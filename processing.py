from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsLineSymbol,
    QgsManhattanLineCallout,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsTask,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont


class ProcessingTask(QgsTask):
    def __init__(
        self,
        description,
        filename,
        content,
        layer_id,
        selected_field,
        branchement_layer_id,
        branchement_selected_field,
    ):
        super().__init__(description)
        self.filename = filename
        self.content = content
        self.layer_id = layer_id
        self.selected_field = selected_field
        self.branchement_layer_id = branchement_layer_id
        self.branchement_selected_field = branchement_selected_field
        self.result_text = ""
        self.error = None

    def run(self):
        try:
            project = QgsProject.instance()
            layer = project.mapLayer(self.layer_id)
            if not layer:
                self.result_text = "La couche sélectionnée est absente"
                return True
            branchement_layer = (
                project.mapLayer(self.branchement_layer_id)
                if hasattr(self, "branchement_layer_id")
                else None
            )
            idx = layer.fields().indexFromName(self.selected_field)
            if idx == -1:
                self.result_text = (
                    f"La couche sélectionée de dispose pas d'attributs "
                    f"'{self.selected_field}'."
                )
                return True
            nr_troncon_geom_map = {}
            for feat in layer.getFeatures():
                nr_value = feat.attribute(self.selected_field)
                if nr_value is not None:
                    nr_troncon_geom_map[str(nr_value)] = feat.geometry()
            nr_branchement_geom_map = {}
            if branchement_layer:
                branchement_idx = branchement_layer.fields().indexFromName(
                    self.branchement_selected_field
                )
                if branchement_idx != -1:
                    for feat in branchement_layer.getFeatures():
                        nr_value = feat.attribute(self.branchement_selected_field)
                        if nr_value is not None:
                            nr_branchement_geom_map[str(nr_value)] = feat.geometry()
            if not nr_troncon_geom_map and not nr_branchement_geom_map:
                self.result_text = "Pas de géométries valides dans les couches."
                return True
            all_line_fields = set()
            all_obs_fields = set()
            unique_observations = set()
            obs_count_per_troncon = {}
            for elem in self.content:
                for key, _ in elem.items():
                    if key != "observation":
                        all_line_fields.add(key)
                numero_troncon = elem.get("numero_troncon")
                if numero_troncon:
                    has_point_depart_lateral = "point_depart_lateral" in elem
                    if (
                        has_point_depart_lateral
                        and numero_troncon in nr_branchement_geom_map
                    ):
                        geom_map = nr_branchement_geom_map
                    elif numero_troncon in nr_troncon_geom_map:
                        geom_map = nr_troncon_geom_map
                    else:
                        continue
                    observations = elem.get("observations", [])
                    valid_obs_count = 0
                    for obs in observations:
                        all_obs_fields.update(obs.keys())
                        unique_observations.add(obs.get("observation", ""))
                        emplacement_long = obs.get("emplacement_longitudinal")
                        if emplacement_long is not None and emplacement_long != "":
                            try:
                                dist = float(emplacement_long)
                                geom = geom_map[numero_troncon]
                                if geom.length() >= dist:
                                    valid_obs_count += 1
                            except ValueError:
                                pass
                    obs_count_per_troncon[numero_troncon] = valid_obs_count
            mem_layer = self._create_observation_layer(layer, all_obs_fields)
            line_layer = self._create_line_layer(layer, all_line_fields)
            point_features = []
            line_features = []
            results = []
            for elem in self.content:
                numero_troncon = elem.get("numero_troncon")
                if not numero_troncon:
                    results.append(f"Information absente 'numero_troncon': {elem}")
                    continue
                has_point_depart_lateral = "point_depart_lateral" in elem
                geom = None
                if (
                    has_point_depart_lateral
                    and numero_troncon in nr_branchement_geom_map
                ):
                    geom = nr_branchement_geom_map[numero_troncon]
                elif numero_troncon in nr_troncon_geom_map:
                    geom = nr_troncon_geom_map[numero_troncon]
                if not geom:
                    results.append(
                        f"Pas de géométrie pour le troncon: {numero_troncon}"
                    )
                    continue
                line_geom = self._process_line_geometry(
                    geom, elem.get("sens_ecoulement", "")
                )
                line_feat = self._create_line_feature(
                    elem,
                    geom,
                    obs_count_per_troncon.get(numero_troncon, 0),
                    line_layer.fields(),
                    all_line_fields,
                )
                line_features.append(line_feat)
                observations = elem.get("observations", [])
                count_added = 0
                for obs in observations:
                    point_feat = self._create_point_feature(
                        obs, line_geom, elem, mem_layer.fields(), all_obs_fields
                    )
                    if point_feat:
                        point_features.append(point_feat)
                        count_added += 1
                results.append(
                    f"Troncon: {numero_troncon} - {count_added} observations ajoutées"
                )
            if line_features:
                line_layer.dataProvider().addFeatures(line_features)
            if point_features:
                mem_layer.dataProvider().addFeatures(point_features)
            line_layer.updateExtents()
            mem_layer.updateExtents()
            project.addMapLayer(line_layer)
            project.addMapLayer(mem_layer)
            self._apply_line_styling(line_layer)
            self._apply_point_styling(mem_layer, unique_observations)
            self._apply_labeling(mem_layer)
            self.result_text = (
                "\n".join(results)
                if results
                else "Pas de géométries ou d'observations trouvées"
            )
            return True
        except Exception as e:
            self.error = e
            return True

    def _create_observation_layer(self, source_layer, obs_fields):
        crs_string = "Point?crs=" + source_layer.crs().authid()
        mem_layer = QgsVectorLayer(crs_string, "Observation", "memory")
        fields = QgsFields()
        for field_name in sorted(obs_fields):
            if field_name == "emplacement_longitudinal":
                fields.append(QgsField(field_name, QVariant.Double))
            else:
                fields.append(QgsField(field_name, QVariant.String))
        mem_layer.dataProvider().addAttributes(fields)
        mem_layer.updateFields()
        return mem_layer

    def _create_line_layer(self, source_layer, line_fields):
        crs_string = "LineString?crs=" + source_layer.crs().authid()
        line_layer = QgsVectorLayer(crs_string, "Inspection", "memory")
        fields = QgsFields()
        fields.append(QgsField("observation_count", QVariant.Int))
        for field_name in sorted(line_fields):
            if field_name in [
                "etendue_inspection_prevue",
                "profondeur_noeud_depart",
                "profondeur_noeud_arrivee",
            ]:
                fields.append(QgsField(field_name, QVariant.Double))
            elif field_name in ["hauteur", "largeur"]:
                fields.append(QgsField(field_name, QVariant.Int))
            else:
                fields.append(QgsField(field_name, QVariant.String))
        line_layer.dataProvider().addAttributes(fields)
        line_layer.updateFields()
        return line_layer

    def _process_line_geometry(self, geom, sens_ecoulement):
        if "amont" not in sens_ecoulement.lower():
            return geom
        if geom.isMultipart():
            lines = geom.asMultiPolyline()
            reversed_lines = [list(reversed(line)) for line in lines]
            return QgsGeometry.fromMultiPolylineXY(reversed_lines)
        else:
            line = geom.asPolyline()
            return QgsGeometry.fromPolylineXY(list(reversed(line)))

    def _create_point_feature(self, obs, line_geom, parent_elem, fields, obs_fields):
        emplacement_long = obs.get("emplacement_longitudinal")
        if emplacement_long is None or emplacement_long == "":
            return None
        try:
            dist = float(emplacement_long)
        except ValueError:
            return None
        if line_geom.length() < dist:
            return None
        point_geom = line_geom.interpolate(dist)
        if point_geom.isEmpty():
            return None
        feat = QgsFeature()
        feat.setGeometry(point_geom)
        feat.setFields(fields)
        for field_name in obs_fields:
            value = obs.get(field_name)
            if value is not None:
                if field_name == "emplacement_longitudinal":
                    feat[field_name] = float(value) if value != "" else None
                else:
                    feat[field_name] = str(value) if value != "" else None
            else:
                feat[field_name] = None
        return feat

    def _create_line_feature(self, elem, geom, obs_count, fields, line_fields):
        feat = QgsFeature()
        feat.setGeometry(geom)
        feat.setFields(fields)
        feat["observation_count"] = obs_count
        for field_name in line_fields:
            value = elem.get(field_name)
            if value is not None:
                if field_name in [
                    "etendue_inspection_prevue",
                    "profondeur_noeud_depart",
                    "profondeur_noeud_arrivee",
                ]:
                    try:
                        feat[field_name] = float(value) if value != "" else None
                    except (ValueError, TypeError):
                        feat[field_name] = None
                elif field_name in ["hauteur", "largeur"]:
                    try:
                        feat[field_name] = int(value) if value != "" else None
                    except (ValueError, TypeError):
                        feat[field_name] = None
                else:
                    feat[field_name] = str(value) if value != "" else None
            else:
                feat[field_name] = None
        return feat

    def _apply_line_styling(self, line_layer):
        symbol = QgsLineSymbol()
        left_line = QgsSimpleLineSymbolLayer.create(
            {"color": "blue", "width": "0.5", "offset": "-1.5"}
        )
        right_line = QgsSimpleLineSymbolLayer.create(
            {"color": "blue", "width": "0.5", "offset": "1.5"}
        )
        symbol.deleteSymbolLayer(0)
        symbol.appendSymbolLayer(left_line)
        symbol.appendSymbolLayer(right_line)
        line_layer.renderer().setSymbol(symbol)
        line_layer.triggerRepaint()

    def _apply_point_styling(self, mem_layer, unique_observations):
        categories = []
        special_obs = {"Type du noeud de départ", "Référence du noeud d'arrivée"}
        for obs_val in unique_observations:
            if obs_val in special_obs:
                symbol = QgsMarkerSymbol.createSimple(
                    {"name": "cross2", "color": "black", "size": "3"}
                )
            else:
                symbol = QgsMarkerSymbol.createSimple(
                    {"name": "circle", "color": "gray", "size": "2"}
                )
            categories.append(QgsRendererCategory(obs_val, symbol, obs_val))
        renderer = QgsCategorizedSymbolRenderer("observation", categories)
        mem_layer.setRenderer(renderer)
        mem_layer.triggerRepaint()

    def _apply_labeling(self, mem_layer):
        label_settings = QgsPalLayerSettings()
        label_settings.fieldName = """
            '<b>' || coalesce("observation", '') || '</b>' ||
            CASE
                WHEN coalesce("caracterisation_1", '') != '' OR
                coalesce("caracterisation_2", '') != ''
                THEN '<p><font size="2">' || coalesce("caracterisation_1", '') ||
                '</p>' ||
                    CASE WHEN coalesce("caracterisation_1", '') != ''
                    AND coalesce("caracterisation_2", '') != ''
                        THEN '<p>' ELSE '' END ||
                    coalesce("caracterisation_2", '') || '</font></p>'
                ELSE ''
            END
        """
        label_settings.isExpression = True
        label_settings.placement = Qgis.LabelPlacement.AroundPoint
        label_settings.placementFlags = Qgis.LabelPredefinedPointPosition.TopRight
        label_settings.dist = 10
        callout = QgsManhattanLineCallout()
        callout.setEnabled(True)
        line_symbol = QgsLineSymbol.createSimple({"color": "black", "width": "0.15"})
        callout.setLineSymbol(line_symbol)
        label_settings.setCallout(callout)
        text_format = QgsTextFormat()
        text_format.setFont(QFont("Arial", 10))
        text_format.setSize(10)
        text_format.setAllowHtmlFormatting(True)
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1.2)
        buffer_settings.setColor(QColor("white"))
        text_format.setBuffer(buffer_settings)
        label_settings.setFormat(text_format)
        labeling = QgsVectorLayerSimpleLabeling(label_settings)
        mem_layer.setLabelsEnabled(True)
        mem_layer.setLabeling(labeling)
        mem_layer.triggerRepaint()


_TXT_HEADER = '#A1=ISO-8859-1:1998\n#A2=fr\n#A3=,\n#A4=.\n#A5="\n'
_B03_HEADER = "ACA,ACB,ACC,ACD,ACE,ACF,ACG,ACH,ACI,ACJ,ACK,ACM"


def _q(value):
    """Wrap a string value in double-quotes for the TXT format."""
    v = str(value).strip() if value else ""
    return f'"{v}"'


def _tube_to_txt(d):
    """Convert one tube dict to its TXT block string."""
    has_aav = "AAV" in d
    b01_header_fields = ["AAA", "AAB", "AAD", "AAF", "AAJ", "AAK", "AAL", "AAM", "AAN"]
    if has_aav:
        b01_header_fields.append("AAV")
    b01_header = ",".join(b01_header_fields)
    b01_values_list = [
        _q(d.get("AAA", "")),
        _q(d.get("AAB", "")),
        _q(d.get("AAD", d.get("AAB", ""))),
        _q(d.get("AAF", "")),
        _q(d.get("AAJ", "")),
        _q(d.get("AAK", "A")),
        d.get("AAL", "Z"),
        d.get("AAM", ""),
        _q(d.get("AAN", "")),
    ]
    if has_aav:
        b01_values_list.append('""')  # empty AAV
    b01_values = ",".join(b01_values_list)
    """b02_value = d.get("ABP", "C")"""
    b02_header_fields = ["ABA","ABC","ABE","ABF","ABG","ABH","ABL","ABM","ABN","ABO","ABP","ABQ","ABR","ABS"]
    b02_header = ",".join(b02_header_fields)
    b02_values_list = [
        d.get("ABA", "EN 13508-2:2003+A1:2011"),
        d.get("ABC", ""),
        d.get("ABE", ""),
        d.get("ABF", ""),
        d.get("ABG", ""),
        d.get("ABH", ""),
        d.get("ABL", ""),
        d.get("ABM", ""),
        d.get("ABN", ""),
        d.get("ABO", ""),
        d.get("ABP", "C"),
        d.get("ABQ", ""),
        d.get("ABR", ""),
        d.get("ABS", ""),
    ]
    b02_values = ",".join(b02_values_list)
    acb = d.get("ACB", "0")
    acc_raw = d.get("ACC", "")
    acc = acc_raw if acc_raw and acc_raw != "0" else acb
    b03_values = ",".join(
        [
            d.get("ACA", "Z"),       
            d.get("ACB", "0"),                     
            acc,                     
            _q(d.get("ACD", "")),      
            "",                      
            "",                      
            d.get("ACG", ""),        
            d.get("ACH", ""),        
            d.get("ACI", ""),        
            "",                      
            d.get("ACK", "Z"),       
            d.get("ACM", ""),        
        ]
    )
    return (
        f"#B01={b01_header}\n"
        f"{b01_values}\n"
        f"#B02={b02_header}\n"
        f"{b02_values}\n"
        f"#B03={_B03_HEADER}\n"
        f"{b03_values}\n"
        f"#Z\n"
    )


_XML_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<DATA>\n"
    "  <ZA>\n"
    "    <A1>UTF-8</A1>\n"
    "    <A2>FRE</A2>\n"
    "    <A4>.</A4>\n"
    "  </ZA>\n"
)
_XML_FOOTER = "</DATA>\n"


def _tube_to_xml(d):
    """Convert one tube dict to its XML <ZB> block (no observations)."""

    def _tag(name, value):
        v = str(value).strip() if value else ""
        return f"    <{name}>{v}</{name}>\n"

    acb = d.get("ACB", "0")
    acc_raw = d.get("ACC", "")
    acc = acc_raw if acc_raw and acc_raw != "0" else acb
    lines = ["  <ZB>\n"]
    lines.append(_tag("AAA", d.get("AAA", "")))
    lines.append(_tag("AAB", d.get("AAB", "")))
    lines.append(_tag("AAD", d.get("AAD", d.get("AAB", ""))))
    lines.append(_tag("AAF", d.get("AAF", "")))
    if d.get("AAJ"):
        lines.append(_tag("AAJ", d.get("AAJ", "")))
    lines.append(_tag("AAK", d.get("AAK", "A")))
    lines.append(_tag("AAL", d.get("AAL", "A")))
    if d.get("AAN"):
        lines.append(_tag("AAN", d.get("AAN", "")))
    lines.append(_tag("ABP", d.get("ABP", "C")))
    lines.append(_tag("ACA", d.get("ACA", "Z")))
    lines.append(_tag("ACB", d.get("ACB", "0")))
    lines.append(_tag("ACC", acc))
    lines.append(_tag("ACD", d.get("ACD", "AX")))
    lines.append(_tag("ACK", d.get("ACK", "Z")))
    if "AAV" in d:
        lines.append(_tag("AAV", ""))
    lines.append("  </ZB>\n")
    return "".join(lines)


class ExportTask(QgsTask):
    """
    QgsTask that writes both the NF EN 13508-2 TXT file and a matching XML
    file in a background thread, mirroring the pattern of ProcessingTask.

    The XML path is derived automatically from the TXT path by swapping the
    extension: e.g. /path/export.txt → /path/export.xml
    """

    def __init__(self, description, tubes, file_path):
        super().__init__(description)
        self.tubes = tubes
        self.file_path = file_path
        self.result_text = ""
        self.error = None

    def _xml_path(self):
        """Derive the .xml sibling path from the .txt path."""
        base = self.file_path
        if base.lower().endswith(".txt"):
            base = base[:-4]
        return base + ".xml"

    def run(self):
        try:
            txt_lines = [_TXT_HEADER]
            for tube in self.tubes:
                txt_lines.append(_tube_to_txt(tube))

            with open(
                self.file_path, "w", encoding="ISO-8859-1", errors="replace"
            ) as f:
                f.write("".join(txt_lines))
            xml_lines = [_XML_HEADER]
            for tube in self.tubes:
                xml_lines.append(_tube_to_xml(tube))
            xml_lines.append(_XML_FOOTER)
            xml_path = self._xml_path()
            with open(xml_path, "w", encoding="UTF-8") as f:
                f.write("".join(xml_lines))
            n = len(self.tubes)
            s = "s" if n > 1 else ""
            self.result_text = (
                f"Export réussi : {n} intervention{s} exportée{s} vers\n"
                f"  TXT : {self.file_path}\n"
                f"  XML : {xml_path}"
            )
            return True
        except Exception as e:
            self.error = e
            return True
