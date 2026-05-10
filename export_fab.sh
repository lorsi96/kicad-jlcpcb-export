#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

source scripts/jlc.env

SCH=${PROJ}.kicad_sch
PCB=${PROJ}.kicad_pcb

mkdir -p output/Gerber output/PnP output/Assembly doc

echo "==> Schematic PDF"
kicad-cli sch export pdf -o doc/schematic.pdf "$SCH"

echo "==> PCB layer PDF"
kicad-cli pcb export pdf \
  --layers "$PCB_LAYERS" \
  -o doc/pcb.pdf "$PCB"

echo "==> Gerbers + drill"
kicad-cli pcb export gerbers -o output/Gerber "$PCB"
kicad-cli pcb export drill   -o output/Gerber "$PCB"

echo "==> CPL (pick-and-place)"
kicad-cli pcb export pos \
  --use-drill-file-origin --format csv --units mm \
  -o output/PnP/${PROJ}-cpl.csv "$PCB"

echo "==> BOM"
kicad-cli sch export bom \
  --fields "Reference,Value,Footprint,LCSC" \
  --group-by "Value,Footprint" \
  -o output/Assembly/${PROJ}-bom.csv "$SCH"

echo "==> Packaging for JLC (zip gerbers, fix CPL rotations)"
python3 scripts/prepare_4_jlc.py

echo ""
echo "Fab outputs ready:"
echo "  output/Gerber/gbr_files.zip       <- JLC: upload as Gerbers"
echo "  output/Assembly/${PROJ}-bom.csv   <- JLC: upload as BOM"
echo "  output/Assembly/${PROJ}-cpl.csv   <- JLC: upload as CPL/PnP"
echo "  doc/schematic.pdf"
echo "  doc/pcb.pdf"
