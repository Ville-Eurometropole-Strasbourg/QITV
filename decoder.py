# ruff: noqa
import os
import xml.etree.ElementTree as ET

from .mapper import (
    caracterisation_1,
    caracterisation_2,
    description_champs,
    etape_inspection,
    format_image,
    format_video,
    forme,
    materiau,
    methode_inspection,
    nettoyage,
    objet_inspection,
    observation,
    point_depart_lateral,
    point_reference_longitudinal,
    position_bande_video,
    precipitations,
    propriete_fonciere,
    regulation_debit,
    sens_ecoulement,
    support_media,
    temperature,
    type_branchement,
    type_emplacement,
    type_revetement,
    utilisation_branchement,
)


class ITVParser:
    VALUE_MAPPINGS = {
        "sens_ecoulement": sens_ecoulement,
        "type_emplacement": type_emplacement,
        "propriete_fonciere": propriete_fonciere,
        "point_depart_lateral": point_depart_lateral,
        "point_reference_longitudinal": point_reference_longitudinal,
        "methode_inspection": methode_inspection,
        "support_media": support_media,
        "format_image": format_image,
        "position_bande_video": position_bande_video,
        "objet_inspection": objet_inspection,
        "format_video": format_video,
        "etape_inspection": etape_inspection,
        "forme": forme,
        "materiau": materiau,
        "type_revetement": type_revetement,
        "type_branchement": type_branchement,
        "utilisation_branchement": utilisation_branchement,
        "nettoyage": nettoyage,
        "precipitations": precipitations,
        "temperature": temperature,
        "regulation_debit": regulation_debit,
        "observation": observation,
    }

    def __init__(self):
        self.segments = []

    def detect_format(self, file_path):
        """Detect file format based on extension and content"""
        _, ext = os.path.splitext(file_path.lower())
        if ext == ".xml":
            return "xml"
        elif ext == ".txt":
            try:
                with open(file_path, encoding="ISO-8859-1") as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("#B01="):
                        return "txt"
            except Exception:
                pass
        try:
            with open(file_path, encoding="ISO-8859-1") as f:
                content = f.read(1000)
                if content.startswith("<?xml") or "<ZB>" in content:
                    return "xml"
                elif "#B01=" in content:
                    return "txt"
        except Exception:
            pass
        raise ValueError(f"Unable to detect format for file: {file_path}")

    def parse_file(self, file_path):
        """Parse ITV file in either XML or TXT format"""
        format_type = self.detect_format(file_path)
        if format_type == "xml":
            return self._parse_xml(file_path)
        elif format_type == "txt":
            return self._parse_txt(file_path)
        else:
            raise ValueError(f"Unsupported format: {format_type}")

    def _get_text_safe(self, element, tag):
        """Safely extract text from XML element"""
        child = element.find(tag)
        return child.text if child is not None and child.text is not None else ""

    def _resolve_characterisation(self, code_principal, field_code, mapping_dict):
        """Resolve characterisation codes"""
        if code_principal in mapping_dict:
            return mapping_dict[code_principal].get(
                field_code, f"Code principal inconnu : '{field_code}'"
            )
        return None

    def _apply_value_mapping(self, field_key, value):
        """Apply value mapping if available"""
        if field_key in self.VALUE_MAPPINGS:
            mapping = self.VALUE_MAPPINGS[field_key]
            return mapping.get(value, value)
        return value

    def _process_segment_data(self, raw_data):
        """Process and clean segment data with proper type conversion"""
        processed_data = {}
        for key, value in raw_data.items():
            field_name = description_champs.get(key, key)
            processed_value = self._apply_value_mapping(field_name, value)
            if field_name == "etendue_inspection_prevue" and processed_value:
                try:
                    processed_value = float(processed_value)
                except ValueError:
                    processed_value = 0.0
            processed_data[field_name] = processed_value
        return processed_data
    
    def _finalize_block(
        self,
        current_block,
        temp_data,
        c_observations
    ):
        if current_block is None:
            return None

        if c_observations:
            current_block["observations"] = c_observations.copy()

        raw_data = {}

        for _, content in temp_data.items():
            keys = content["header"]
            values = content["values"]

            if values is None:
                continue

            for k, v in zip(keys, values):
                raw_data[k] = v

        if raw_data:
            processed_block = self._process_segment_data(raw_data)
            current_block.update(processed_block)

        return current_block

    def _parse_xml(self, file_path):
        """Parse XML format ITV file"""
        tree = ET.parse(file_path)
        root = tree.getroot()
        segments = []
        for zb in root.findall("ZB"):
            raw_data = {}
            for field_code, _ in description_champs.items():
                if field_code in [
                    "A",
                    "B",
                    "C",
                    "D",
                    "E",
                    "F",
                    "G",
                    "H",
                    "I",
                    "J",
                    "K",
                    "L",
                    "M",
                    "N",
                ]:
                    continue
                raw_data[field_code] = self._get_text_safe(zb, field_code)
            segment_data = self._process_segment_data(raw_data)
            zc_list = []
            for zc in zb.findall("ZC"):
                zc_data = {
                    "observation": self._apply_value_mapping(
                        "observation", self._get_text_safe(zc, "A")
                    ),
                    "caracterisation_1": self._resolve_characterisation(
                        self._get_text_safe(zc, "A"),
                        self._get_text_safe(zc, "B"),
                        caracterisation_1,
                    ),
                    "caracterisation_2": self._resolve_characterisation(
                        self._get_text_safe(zc, "A"),
                        self._get_text_safe(zc, "C"),
                        caracterisation_2,
                    ),
                    "quantification_1": self._get_text_safe(zc, "D"),
                    "quantification_2": self._get_text_safe(zc, "E"),
                    "remarques": self._get_text_safe(zc, "F"),
                    "emplacement_circonf_1": self._get_text_safe(zc, "G"),
                    "emplacement_circonf_2": self._get_text_safe(zc, "H"),
                    "emplacement_longitudinal": self._get_text_safe(zc, "I"),
                    "code_defaut_continu": self._get_text_safe(zc, "J"),
                    "assemblage": self._get_text_safe(zc, "K"),
                    "champ_description_emplacement": self._get_text_safe(zc, "L"),
                    "ref_photo": self._get_text_safe(zc, "M"),
                    "ref_video": self._get_text_safe(zc, "N"),
                }
                zc_list.append(zc_data)
            segment_data["observations"] = zc_list
            segments.append(segment_data)
        return segments

    def _parse_txt(self, file_path):
        """Parse TXT format ITV file"""
        with open(file_path, encoding="ISO-8859-1") as f:
            lines = f.readlines()
        blocks = []
        current_block = None
        temp_data = {}
        last_b_key = None
        c_header_keys = []
        c_observations = []
        separator = ";"
        quote = '"'
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#A3="):
                separator = line[len("#A3="):].strip()
            elif line.startswith("#A5="):
                quote = line[len("#A5="):].strip()
            if line.startswith("#B01="):
                if current_block:
                    blocks.append(current_block)
                current_block = {}
                temp_data.clear()
                c_observations.clear()
                c_header_keys.clear()
                last_b_key = "B01"
                header_keys = line[len("#B01=") :].split(separator)
                header_keys = [h.strip(quote) for h in header_keys]
                temp_data["B01"] = {"header": header_keys, "values": None}
            elif line.startswith("#B02="):
                last_b_key = "B02"
                header_keys = line[len("#B02=") :].split(separator)
                header_keys = [h.strip(quote) for h in header_keys]
                temp_data["B02"] = {"header": header_keys, "values": None}
            elif line.startswith("#B03="):
                last_b_key = "B03"
                header_keys = line[len("#B03=") :].split(separator)
                header_keys = [h.strip(quote) for h in header_keys]
                temp_data["B03"] = {"header": header_keys, "values": None}
            elif line.startswith("#C="):
                last_b_key = "C"
                c_header_keys = line[len("#C=") :].split(separator)
                c_header_keys = [h.strip(quote) for h in c_header_keys]
            elif line == "#Z":
                block = self._finalize_block(
                    current_block,
                    temp_data,
                    c_observations
                )

                if block:
                    blocks.append(block)

                temp_data.clear()
                c_observations.clear()
                c_header_keys.clear()
                last_b_key = None
                current_block = None
            else:
                if last_b_key == "C" and c_header_keys:
                    values = line.split(separator)
                    values = [v.strip(quote) for v in values]
                    observation_data = {}
                    for _, (key, value) in enumerate(zip(c_header_keys, values)):
                        if key in description_champs:
                            field_name = description_champs[key]
                            observation_data[field_name] = value
                    if "observation" in observation_data:
                        obs_code = observation_data["observation"]
                        observation_data["observation"] = self._apply_value_mapping(
                            "observation", obs_code
                        )
                        if "caracterisation_1" in observation_data:
                            observation_data["caracterisation_1"] = (
                                self._resolve_characterisation(
                                    obs_code,
                                    observation_data["caracterisation_1"],
                                    caracterisation_1,
                                )
                            )
                        if "caracterisation_2" in observation_data:
                            observation_data["caracterisation_2"] = (
                                self._resolve_characterisation(
                                    obs_code,
                                    observation_data["caracterisation_2"],
                                    caracterisation_2,
                                )
                            )
                    c_observations.append(observation_data)
                elif last_b_key and last_b_key in temp_data:
                    values = line.split(separator)
                    values = [v.strip(quote) for v in values]
                    temp_data[last_b_key]["values"] = values
        block = self._finalize_block(
            current_block,
            temp_data,
            c_observations
        )

        if block:
            blocks.append(block)

        return blocks


def itv_parser(xml_data):
    return ITVParser().parse_file(xml_data)
