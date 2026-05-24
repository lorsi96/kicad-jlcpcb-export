"""Post-process KiCad exports for JLCPCB upload.

Run from the repo root:
    python3 scripts/prepare_4_jlc.py

Reads:
  output/Gerber/*.gbr / *.drl  -> zipped into output/Gerber/gbr_files.zip
  output/PnP/*-cpl.csv         -> column headers renamed, rotations corrected
  output/Assembly/*-bom.csv    -> column headers renamed
  scripts/rotation_offsets.csv

Writes:
  output/Gerber/gbr_files.zip
  output/Assembly/*-cpl.csv    (JLC-ready CPL)
  output/Assembly/*-bom.csv    (JLC-ready BOM, in place)
"""

import csv
import logging
import re
import shutil
import zipfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger()

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
GERBER_DIR = REPO_ROOT / "output" / "Gerber"
PNP_DIR = REPO_ROOT / "output" / "PnP"
ASSEMBLY_DIR = REPO_ROOT / "output" / "Assembly"
ROTATION_CSV = SCRIPT_DIR / "rotation_offsets.csv"

GERBER_SUFFIXES = {"gtl", "g1", "g2", "g3", "gbl", "gta", "gba", "gtp", "gbp",
                   "gto", "gbo", "gts", "gbs", "gbr", "gm1", "drl", "gbrjob"}

CPL_COLUMN_RENAMES = {
    "Ref": "Designator",
    "PosX": "Mid X",
    "PosY": "Mid Y",
    "Rot": "Rotation",
    "Side": "Layer",
}

BOM_COLUMN_RENAMES = {
    "Reference": "Designator",
    "Value": "Comment",
}


def load_rotation_offsets():
    """Return a dict keyed by designator.

    Each value is a dict with keys:
      ``offset``   – rotation correction in degrees (int)
      ``x_offset`` – correction added to Mid X in mm (int, default 0)
      ``y_offset`` – correction added to Mid Y in mm (int, default 0)
    """
    offsets = {}
    if not ROTATION_CSV.exists():
        return offsets
    with open(ROTATION_CSV, newline="") as f:
        for row in csv.DictReader(r for r in f if not r.startswith("#")):
            offsets[row["Designator"].strip()] = {
                "offset":   int(row["Offset"].strip()),
                "x_offset": int(row.get("x_offset", "0").strip() or "0"),
                "y_offset": int(row.get("y_offset", "0").strip() or "0"),
            }
    logger.info("Loaded %d rotation offsets", len(offsets))
    return offsets


def zip_gerbers():
    gbr_files = [f for f in GERBER_DIR.iterdir()
                 if f.suffix.lstrip(".").lower() in GERBER_SUFFIXES]
    if not gbr_files:
        logger.warning("No gerber/drill files found in %s", GERBER_DIR)
        return
    zip_path = GERBER_DIR / "gbr_files.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in gbr_files:
            zf.write(f, f.name)
    logger.info("Created %s (%d files)", zip_path, len(gbr_files))


def fix_cpl(rotation_offsets):
    ASSEMBLY_DIR.mkdir(parents=True, exist_ok=True)
    cpl_files = list(PNP_DIR.glob("*-cpl.csv")) + list(PNP_DIR.glob("*pos.csv"))
    if not cpl_files:
        logger.warning("No CPL/pos CSV files found in %s", PNP_DIR)
        return

    for src in cpl_files:
        dest = ASSEMBLY_DIR / src.name
        shutil.copy(src, dest)
        logger.info("Processing %s -> %s", src.name, dest)

        lines = dest.read_text().splitlines()
        out = []
        for i, line in enumerate(lines):
            if i == 0:
                headers = line.split(",")
                headers = [CPL_COLUMN_RENAMES.get(h.strip(), h.strip()) for h in headers]
                out.append(",".join(headers))
                continue
            row = line.split(",")
            if len(row) < 6:
                out.append(line)
                continue
            designator = row[0].strip('"')
            try:
                rotation = int(float(row[5]))
            except ValueError:
                out.append(line)
                continue
            if designator in rotation_offsets:
                corr = rotation_offsets[designator]
                rotation = (rotation + corr["offset"]) % 360
                x_off = corr["x_offset"]
                y_off = corr["y_offset"]
                if x_off:
                    row[3] = str(float(row[3]) + x_off)
                if y_off:
                    row[4] = str(float(row[4]) + y_off)
                logger.info(
                    "  %s rotation -> %d, x_offset %+d, y_offset %+d",
                    designator, rotation, x_off, y_off,
                )
            row[5] = str(rotation)
            out.append(",".join(row))
        dest.write_text("\n".join(out) + "\n")

    logger.info("CPL files written to %s", ASSEMBLY_DIR)


def _expand_designator_ranges(designator_str: str) -> str:
    """Expand dash-range shorthand to explicit comma-separated designators.

    KiCad sometimes emits e.g. ``SW1-SW3`` or ``R3-R5,R12-R15``.
    JLCPCB requires ``SW1,SW2,SW3`` / ``R3,R4,R5,R12,R13,R14,R15``.
    """
    parts = [p.strip() for p in designator_str.split(",")]
    out = []
    for part in parts:
        m = re.fullmatch(r"([A-Za-z]+)(\d+)-(?:[A-Za-z]+)?(\d+)", part)
        if m:
            prefix, start, end = m.group(1), int(m.group(2)), int(m.group(3))
            out.extend(f"{prefix}{n}" for n in range(start, end + 1))
            logger.info("  Expanded range %s -> %s", part,
                        ",".join(f"{prefix}{n}" for n in range(start, end + 1)))
        else:
            out.append(part)
    return ",".join(out)


def fix_bom():
    bom_files = list(ASSEMBLY_DIR.glob("*-bom.csv"))
    if not bom_files:
        logger.warning("No BOM CSV files found in %s", ASSEMBLY_DIR)
        return
    for bom in bom_files:
        logger.info("Processing BOM %s", bom.name)
        lines = bom.read_text().splitlines()
        out = []
        for i, line in enumerate(lines):
            if i == 0:
                headers = line.split(",")
                headers = [BOM_COLUMN_RENAMES.get(h.strip().strip('"'), h.strip()) for h in headers]
                out.append(",".join(headers))
            else:
                # Parse with csv to correctly handle quoted fields containing commas.
                row = next(csv.reader([line]))
                if row:
                    row[0] = _expand_designator_ranges(row[0])
                # Re-quote all fields to stay consistent with KiCad's output style.
                out.append(",".join(f'"{v}"' for v in row))
        bom.write_text("\n".join(out) + "\n")
    logger.info("BOM files updated in %s", ASSEMBLY_DIR)


if __name__ == "__main__":
    rotation_offsets = load_rotation_offsets()
    zip_gerbers()
    fix_cpl(rotation_offsets)
    fix_bom()
    logger.info("Done.")
