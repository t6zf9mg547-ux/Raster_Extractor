#!/usr/bin/env python3
"""
Raster Extractor
----------------
For each dam in an input CSV, clips a user-selected raster (.tif) to that
dam's watershed boundary (a GeoParquet polygon) and reports basic raster
statistics.

Project layout (matches Watershed Generator / Downstream River Course
conventions):
    Raster_Extractor/
        Module/   <- this script lives here; project root = script's parent.parent
        Output/   <- {csv_stem}_output.csv (QC_flag, status, clipped raster stats)
        Plot/     <- {csv_stem}/{Dam_ID}_clip.tif  (one clipped raster per dam)

Watershed file matching: files in the watershed folder are matched by
filename PREFIX "{Dam_ID}_*" (the suffix after the ID is not fixed, e.g.
"1234_watershed.parquet", "1234_basin_v2.parquet", ...). If zero or more than
one file matches a given Dam_ID, that dam is flagged as an error and
skipped rather than guessed at.

Interactive mode (no CLI args): opens tkinter file dialogs to pick the
CSV, watershed folder, and source raster, with a typed-input fallback if
tkinter is unavailable (e.g. headless environments).

Usage:
    python RasterExtractor.py
    python RasterExtractor.py --csv dams.csv --watershed-folder /path/to/watersheds --raster /path/to/source.tif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask

SAVE_EVERY = 10
DAM_ID_COL = "Dam ID"


# ---------------------------------------------------------------------------
# Interactive selection (tkinter with typed-input fallback)
#
# macOS's native file dialog doesn't reliably display the `title` text on
# the panel itself, so instructions are printed to the terminal right
# before each picker opens, instead of a popup alert.
# ---------------------------------------------------------------------------
def _pick_file(title: str, message: str, filetypes, initialdir: Path | None = None) -> Path:
    print(f"\n{title}\n{message}")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        kwargs = {"title": title, "filetypes": filetypes}
        if initialdir is not None and initialdir.exists():
            kwargs["initialdir"] = str(initialdir)
        path = filedialog.askopenfilename(**kwargs)
        root.destroy()
        if path:
            return Path(path)
    except Exception:
        pass
    typed = input("Path: ").strip()
    return Path(typed)


def _pick_folder(title: str, message: str, initialdir: Path | None = None) -> Path:
    print(f"\n{title}\n{message}")
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        kwargs = {"title": title}
        if initialdir is not None and initialdir.exists():
            kwargs["initialdir"] = str(initialdir)
        path = filedialog.askdirectory(**kwargs)
        root.destroy()
        if path:
            return Path(path)
    except Exception:
        pass
    typed = input("Path: ").strip()
    return Path(typed)


def get_inputs(project_root: Path) -> tuple[Path, Path, Path]:
    parser = argparse.ArgumentParser(
        description="Clip a raster to each dam's watershed boundary."
    )
    parser.add_argument("--csv", type=Path, help="Input CSV with a 'Dam ID' column")
    parser.add_argument(
        "--watershed-folder",
        type=Path,
        help="Folder containing {Dam_ID}_* watershed boundary .parquet files",
    )
    parser.add_argument("--raster", type=Path, help="Source raster (.tif) to clip")
    args = parser.parse_args()

    data_dir = project_root / "Data"

    csv_path = args.csv or _pick_file(
        "Step 1 of 3 — Select input CSV",
        "Choose the CSV file listing the dams to process.\n"
        "It must include a 'Dam ID' column.\n\n"
        "This is usually in the project's Data/ folder.",
        [("CSV files", "*.csv"), ("All files", "*.*")],
        initialdir=data_dir,
    )
    watershed_folder = args.watershed_folder or _pick_folder(
        "Step 2 of 3 — Select watershed folder",
        "Choose the folder containing the watershed boundary .parquet files.\n"
        "Each file must be named like '{Dam_ID}_...parquet'\n"
        "(e.g. DS0001001_watershed_257553km2.parquet).",
        initialdir=data_dir,
    )
    raster_path = args.raster or _pick_file(
        "Step 3 of 3 — Select source raster",
        "Choose the source raster (.tif) that will be clipped\n"
        "to each dam's watershed boundary.",
        [("GeoTIFF", "*.tif"), ("All files", "*.*")],
        initialdir=data_dir,
    )

    return csv_path, watershed_folder, raster_path


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------
def find_watershed_matches(watershed_folder: Path, dam_id: str) -> list[Path]:
    """Match watershed .parquet file(s) by filename PREFIX '{dam_id}_*'."""
    return sorted(watershed_folder.glob(f"{dam_id}_*.parquet"))


def clip_raster_to_geometry(raster_path: Path, gdf: gpd.GeoDataFrame, out_path: Path) -> dict:
    """Clip raster_path to gdf's dissolved geometry; write out_path; return stats."""
    with rasterio.open(raster_path) as src:
        gdf_reproj = gdf.to_crs(src.crs)
        try:
            union_geom = gdf_reproj.geometry.union_all()
        except AttributeError:  # older geopandas
            union_geom = gdf_reproj.geometry.unary_union

        out_image, out_transform = mask(src, [union_geom], crop=True, nodata=src.nodata)
        out_meta = src.meta.copy()
        out_meta.update(
            {
                "height": out_image.shape[1],
                "width": out_image.shape[2],
                "transform": out_transform,
            }
        )
        nodata = src.nodata

    band = out_image[0].astype("float64")
    if nodata is not None:
        valid = band[band != nodata]
    elif np.issubdtype(out_image.dtype, np.floating):
        valid = band[~np.isnan(band)]
    else:
        valid = band.ravel()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(out_image)

    if valid.size == 0:
        return {"mean": np.nan, "min": np.nan, "max": np.nan, "sum": np.nan, "valid_pixel_count": 0}

    return {
        "mean": float(valid.mean()),
        "min": float(valid.min()),
        "max": float(valid.max()),
        "sum": float(valid.sum()),
        "valid_pixel_count": int(valid.size),
    }


def main() -> None:
    # Project root = parent of this script's own Module/ folder
    project_root = Path(__file__).resolve().parent.parent

    csv_path, watershed_folder, raster_path = get_inputs(project_root)

    for label, p in [("CSV", csv_path), ("Watershed folder", watershed_folder), ("Raster", raster_path)]:
        if not p.exists():
            sys.exit(f"{label} not found: {p}")

    output_dir = project_root / "Output"
    plot_dir = project_root / "Plot" / csv_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_dir.mkdir(parents=True, exist_ok=True)

    out_csv_path = output_dir / f"{csv_path.stem}_output.csv"

    df = pd.read_csv(csv_path, dtype={DAM_ID_COL: str})
    if DAM_ID_COL not in df.columns:
        sys.exit(f"Column '{DAM_ID_COL}' not found in {csv_path.name}")

    # New columns appended by this tool. All original input CSV columns
    # (Dam name, Latitude, Longitude, Area_km2, etc.) are carried through
    # to the output unchanged, in addition to these.
    new_cols = ["QC_flag", "status", "clip_tif_path", "mean", "min", "max", "sum", "valid_pixel_count"]
    result_cols = list(df.columns) + [c for c in new_cols if c not in df.columns]

    # Resume support: reuse existing output, skip dams already processed
    # (QC_flag not NaN, whether the prior attempt succeeded or failed).
    if out_csv_path.exists():
        results = pd.read_csv(out_csv_path, dtype={DAM_ID_COL: str})
    else:
        results = pd.DataFrame(columns=result_cols)

    processed_ids = set(results.loc[results["QC_flag"].notna(), DAM_ID_COL]) if not results.empty else set()

    rows = []
    for _, row in df.iterrows():
        dam_id = str(row[DAM_ID_COL])
        if dam_id in processed_ids:
            continue

        input_fields = row.to_dict()
        matches = find_watershed_matches(watershed_folder, dam_id)
        out_tif = plot_dir / f"{dam_id}_clip.tif"

        if len(matches) == 0:
            rows.append({
                **input_fields, "QC_flag": "ERROR", "status": "No watershed .parquet found",
                "clip_tif_path": "", "mean": np.nan, "min": np.nan, "max": np.nan,
                "sum": np.nan, "valid_pixel_count": 0,
            })
        elif len(matches) > 1:
            rows.append({
                **input_fields, "QC_flag": "ERROR",
                "status": f"Ambiguous match: {len(matches)} .parquet files found",
                "clip_tif_path": "", "mean": np.nan, "min": np.nan, "max": np.nan,
                "sum": np.nan, "valid_pixel_count": 0,
            })
        else:
            try:
                gdf = gpd.read_parquet(matches[0])
                stats = clip_raster_to_geometry(raster_path, gdf, out_tif)
                rows.append({
                    **input_fields, "QC_flag": "OK", "status": "Clipped successfully",
                    "clip_tif_path": str(out_tif), **stats,
                })
            except Exception as exc:
                rows.append({
                    **input_fields, "QC_flag": "ERROR", "status": str(exc),
                    "clip_tif_path": "", "mean": np.nan, "min": np.nan, "max": np.nan,
                    "sum": np.nan, "valid_pixel_count": 0,
                })

        if len(rows) >= SAVE_EVERY:
            new_rows = pd.DataFrame(rows)
            results = new_rows.copy() if results.empty else pd.concat([results, new_rows], ignore_index=True)
            results.to_csv(out_csv_path, index=False)
            rows = []

    if rows:
        new_rows = pd.DataFrame(rows)
        results = new_rows.copy() if results.empty else pd.concat([results, new_rows], ignore_index=True)
        results.to_csv(out_csv_path, index=False)

    print(f"Done. Output CSV: {out_csv_path}")
    print(f"Clipped rasters: {plot_dir}")


if __name__ == "__main__":
    main()