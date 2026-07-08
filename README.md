# Raster Extractor

Clips a source raster (`.tif`) to each dam's watershed boundary and reports
basic raster statistics per dam, across a global dam portfolio.

## What it does

For every dam listed in an input CSV:

1. Looks up that dam's watershed boundary — a GeoParquet polygon file in a
   given folder, matched by filename prefix `{Dam ID}_*.parquet`
   (e.g. `DS0001001_watershed_257553km2.parquet`).
2. Clips the source raster to that boundary.
3. Writes the clipped raster as a GeoTIFF.
4. Computes basic stats (mean, min, max, sum, valid pixel count) over the
   clipped area.
5. Logs a QC flag and status per dam to an output CSV.

Dams with no matching watershed file, or more than one match, are flagged
as errors rather than guessed at.

## Project layout

```
Raster_Extractor/
├── Data/     # inputs: CSV, watershed parquet files, source raster
├── Module/   # RasterExtractor.py (this tool)
├── Output/   # {csv_stem}_output.csv — QC_flag, status, stats per dam
├── Plot/     # {csv_stem}/{Dam_ID}_clip.tif — one clipped raster per dam
└── pyproject.toml
```

## Setup

```
uv sync
```

Requires GDAL at the system level (for `fiona`/`rasterio`):

```
brew install gdal
```

## Usage

Interactive (opens file pickers for the CSV, watershed folder, and raster):

```
uv run Module/RasterExtractor.py
```

Or pass everything as arguments:

```
uv run Module/RasterExtractor.py \
    --csv Data/dams.csv \
    --watershed-folder Data/watersheds \
    --raster Data/source.tif
```

## Input requirements

- **CSV**: must include a `Dam ID` column.
- **Watershed folder**: one GeoParquet file per dam, filename starting with
  `{Dam ID}_` (the rest of the filename is free-form).
- **Raster**: any GDAL-readable `.tif`; reprojected on the fly to match the
  watershed boundary's CRS.

## Output

- `Output/{csv_stem}_output.csv` — one row per dam: `Dam ID`, `QC_flag`,
  `status`, `clip_tif_path`, `mean`, `min`, `max`, `sum`,
  `valid_pixel_count`.
- `Plot/{csv_stem}/{Dam_ID}_clip.tif` — the clipped raster per dam.

Processing saves progressively every 10 dams. Re-running on an existing
output CSV skips dams already processed (whether they succeeded or failed).