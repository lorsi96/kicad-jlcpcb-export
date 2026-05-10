# kicad-jlcpcb-scripts

Scripts for exporting KiCad 9.x projects to JLCPCB-ready fab outputs — gerbers,
BOM, and CPL — with no external Python dependencies.

## Requirements

- KiCad 9.x (`kicad-cli` on `PATH`)
- Python 3.x (stdlib only)

## Usage

```bash
./scripts/export_fab.sh
```

Run from anywhere — the script `cd`s to the repo root automatically.

### Output

| File | Upload to JLC as |
|---|---|
| `output/Gerber/gbr_files.zip` | Gerber files |
| `output/Assembly/<PROJ>-bom.csv` | BOM |
| `output/Assembly/<PROJ>-cpl.csv` | CPL / Pick-and-place |
| `doc/schematic.pdf` | — |
| `doc/pcb.pdf` | — |

## Configuration

### `jlc.env`

Project-specific variables sourced by `export_fab.sh`:

| Variable | Description |
|---|---|
| `PROJ` | Stem of your `.kicad_sch` / `.kicad_pcb` files |
| `PCB_LAYERS` | Comma-separated list of layers exported to the PDF |

### `rotation_offsets.csv`

Per-designator rotation corrections (degrees) applied to the CPL. JLC's part
orientations often differ from KiCad's footprint convention. Add one row per
affected part:

```csv
Designator,Offset
U1,270
J1,90
```

Lines starting with `#` are ignored. Common offenders: ESP32 modules, USB-C
connectors, terminal blocks, QFN packages.

## How it works

`export_fab.sh` calls `kicad-cli` to produce raw exports, then hands off to
`prepare_4_jlc.py` which:

1. Zips all gerber/drill files into `output/Gerber/gbr_files.zip`
2. Renames CPL columns to JLC's expected names and applies rotation offsets
3. Renames BOM columns to JLC's expected names (`Value→Comment`, `Reference→Designator`)

The LCSC part number for each component is read directly from the `LCSC` field
in your KiCad schematic symbols and passed through to the BOM unchanged.
