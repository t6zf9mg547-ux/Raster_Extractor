# Raster Extractor

Clips a source raster to each dam's watershed boundary and reports
basic raster statistics per dam, across a global dam portfolio. The source
can be a plain `.tif`/`.tiff`, or a `.tar`/`.tar.gz`/`.tgz` archive
containing one (e.g. an OpenTopography COP30 download).

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
├── Data/
│   ├── _extracted/   # cached extraction of .tar source rasters (auto-created)
│   └── ...           # CSV, watershed parquet files, source raster/archive
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

A `.tar` archive works the same way:

```
uv run Module/RasterExtractor.py \
    --csv Data/dams.csv \
    --watershed-folder Data/watersheds \
    --raster Data/rasters_COP30.tar
```

## Input requirements

- **CSV**: must include a `Dam ID` column.
- **Watershed folder**: one GeoParquet file per dam, filename starting with
  `{Dam ID}_` (the rest of the filename is free-form).
- **Raster**: any GDAL-readable `.tif`/`.tiff`, reprojected on the fly to
  match the watershed boundary's CRS. A `.tar`/`.tar.gz`/`.tgz` archive
  containing a single raster is also accepted — it's extracted once into
  `Data/_extracted/{archive_stem}/` and the cached extraction is reused on
  later runs. If an archive contains more than one raster, the first one
  found is used and a warning is printed.

## Output

- `Output/{csv_stem}_output.csv` — one row per dam: all original input CSV
  columns (`Dam ID`, `Dam name`, `Latitude`, `Longitude`, `Area_km2`, etc.)
  are carried through unchanged, plus new columns appended: `QC_flag`,
  `status`, `clip_tif_path`, `mean`, `min`, `max`, `sum`,
  `valid_pixel_count`.
- `Plot/{csv_stem}/{Dam_ID}_clip.tif` — the clipped raster per dam.

Processing saves progressively every 10 dams. Re-running on an existing
output CSV skips dams already processed (whether they succeeded or failed).