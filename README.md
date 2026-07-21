# Nexgrid to SQL CSV Importer

## Overview
This tool reads a monthly Nexgrid CSV and inserts rows into a SQL Server database. The CSV should be placed in the `nexgrid_hourly_reports_monthly` folder which can be accessed after unzipping the release build `.zip` file. Processed files are automatically moved to the `archive` folder. No Python installation needed if you use the bundled EXE.

## Getting Started

Using the packaged release (`nexgrid_importer_*.zip`):

1. Unzip the package
2. Place your monthly CSV file in the `incoming` folder
3. It will be processed on a regular basis, or you can double-click `run_export.bat` for instant processing
4. The script processes the CSV and moves it to `archive`

## Alternative: Direct EXE Usage

You can also double-click `export_pipeline.exe` directly, but the batch wrapper (`run_export.bat`) is recommended for automatic archiving.

## Behind the Scenes

The packaged EXE (`export_pipeline.exe`) contains:
- Python 3 interpreter
- All required packages (pandas, pyodbc, shapely, etc.)
- CSV import script

When you run the EXE or the batch file, it extracts and executes everything for you.

## Requirements

- **Recipient machine**: Windows only (exe includes Python; no install needed)
- **SQL Server**: Approved Windows user account with access to target database
- **Python** (only if building the EXE yourself or running the script directly): Python 3.8+

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Error: file not found` | Check CSV file name and location in `incoming` |
| `Error: input must be a .csv file` | Ensure the file has `.csv` extension |
| Script processes nothing | Verify CSV columns: `meter_id`, `time`, `kwh usage` |
| Antivirus blocks EXE | This is a common false positive with PyInstaller builds. Add `export_pipeline.exe` to antivirus whitelist. |

## To Do
- Add Mac support
- Add toggle for other types of read periods (e.g., daily, weekly)
- Pipe output to a real-time dashboard with geospatial analysis maps, graphs, etc.
- In the real-time dashboard, provide a way for internal users to upload their `.csv` reports
