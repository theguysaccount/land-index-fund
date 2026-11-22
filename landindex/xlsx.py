"""A minimal .xlsx reader (zip + XML, standard library only): sheet names and rows of cell strings.

Enough for a plain data workbook such as FHFA's land price file. Formulas come back as their cached values.
"""
import zipfile
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class Workbook(object):
    def __init__(self, path):
        self.zip = zipfile.ZipFile(path)
        self._strings = None
        wb = ET.fromstring(self.zip.read("xl/workbook.xml"))
        rels = ET.fromstring(self.zip.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels.iter(PNS + "Relationship")}
        self.sheets = []
        for s in wb.find(NS + "sheets"):
            target = targets.get(s.get(RNS + "id"), "")
            part = target.lstrip("/") if target.startswith("/") else "xl/" + target
            self.sheets.append((s.get("name") or "", part))

    def close(self):
        self.zip.close()

    def strings(self):
        if self._strings is None:
            out = []
            if "xl/sharedStrings.xml" in self.zip.namelist():
                with self.zip.open("xl/sharedStrings.xml") as fh:
                    for _, el in ET.iterparse(fh):
                        if el.tag == NS + "si":
                            out.append("".join(t.text or "" for t in el.iter(NS + "t")))
                            el.clear()
            self._strings = out
        return self._strings

    def find(self, wanted):
        """Sheet whose name matches `wanted`, ignoring case and surrounding spaces. None when absent."""
        key = " ".join(wanted.lower().split())
        for name, part in self.sheets:
            if " ".join(name.lower().split()) == key:
                return part
        return None

    def rows(self, part):
        """Yield each row as a list of strings (None for empty cells), padded by column position."""
        strings = self.strings()
        with self.zip.open(part) as fh:
            for _, el in ET.iterparse(fh):
                if el.tag != NS + "row":
                    continue
                row = []
                for c in el.findall(NS + "c"):
                    idx = _col(c.get("r") or "")
                    if idx < 0:
                        idx = len(row)
                    while len(row) < idx:
                        row.append(None)
                    kind = c.get("t")
                    v = c.find(NS + "v")
                    if kind == "s" and v is not None and v.text is not None:
                        val = strings[int(v.text)]
                    elif kind == "inlineStr":
                        val = "".join(t.text or "" for t in c.iter(NS + "t"))
                    elif v is not None:
                        val = v.text
                    else:
                        val = None
                    row.append(val)
                yield row
                el.clear()


def _col(ref):
    n = 0
    for ch in ref:
        if ch.isalpha():
            n = n * 26 + ord(ch.upper()) - 64
        else:
            break
    return n - 1
