# Nexgrid to SQL CSV Importer
![Static Badge](https://img.shields.io/badge/version-1.1-blue)

## Overview
This tool reads a monthly Nexgrid CSV and inserts rows into a SQL Server database. The CSV should be placed in the `incoming` folder which can be accessed after unzipping the release build `.zip` file. Processed files are automatically moved to the `archive` folder. No Python installation needed if you use the bundled EXE.

## Getting Started

Using the packaged release (`nexgrid_importer_*.zip`):

1. Unzip the package
2. Place your monthly CSV file in the `incoming` folder
3. It will be processed on a regular basis, or you can double-click `run_export.bat` for instant processing
4. The script processes the CSV and moves it to `archive`

## Alternative: Bundled Usage

You can use the bundled `dist\export_pipeline\export_pipeline.exe` or simply run the batch wrapper (`run_export.bat`) for automatic archiving.

## Behind the Scenes

The packaged onedir bundle contains:
- `export_pipeline.exe`
- Python runtime files
- All required packages (pandas, pyodbc, shapely, etc.)
- CSV import script

When you run the executable or the batch file, the application loads from the bundle directory and executes without needing a system Python install.

## Requirements

- **Recipient machine**: Windows only (exe includes Python; no install needed)
- **SQL Server**: Approved Windows user account with access to target database
- **Python** (_only if building the EXE yourself or running the script directly_): Python 3.8+

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Error: file not found` | Check CSV file name and location in `incoming` |
| `Error: input must be a .csv file` | Ensure the file has `.csv` extension |
| Script processes nothing | Verify CSV columns: `meter_id`, `time`, `kwh usage` |
| Antivirus blocks EXE | This is a common false positive with PyInstaller builds. Add `export_pipeline.exe` to antivirus whitelist. |

## Development

If you fork this code and update it, run `build.bat` followed by `package_release.bat` to generate the `nexgrid_importer.zip` file with all necessary release files.

## To Do
- Add Mac support
- Add toggle for other types of read periods (e.g., daily, weekly)
- Pipe output to a real-time dashboard with geospatial analysis maps, graphs, etc.
- In the real-time dashboard, provide a way for internal users to upload their `.csv` reports
