<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**

- [Nexgrid to SQL CSV Importer](#nexgrid-to-sql-csv-importer)
  - [Overview](#overview)
  - [Getting Started](#getting-started)
  - [Alternative: Bundled Usage](#alternative-bundled-usage)
  - [Behind the Scenes](#behind-the-scenes)
  - [Requirements](#requirements)
  - [Troubleshooting](#troubleshooting)
  - [Development](#development)
  - [To Do](#to-do)
- [Transformer Risk Dashboard](#transformer-risk-dashboard)
  - [Overview](#overview-1)
  - [Pre-requisites](#pre-requisites)
  - [How to Launch the Dashboard](#how-to-launch-the-dashboard)
  - [Using the Dashboard](#using-the-dashboard)
  - [Important Notes](#important-notes)
  - [To Do](#to-do-1)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

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

---

# Transformer Risk Dashboard
![Static Badge](https://img.shields.io/badge/version-1.0-blue)

## Overview

This tool helps identify transformers that are at risk of overloading during hot weather periods. It is designed to run locally on an MMLD workstation to ensure a secure, trusted connection to the internal database server (MMLDAPP03).

## Pre-requisites

**Python 3.8+**: Install Python on your Windows machine following the steps below.
1.	Open the Microsoft Store application.
2.	Search for Python in the search bar. You will see several versions. Select the latest stable version published by the Python Software Foundation (https://www.python.org/psf-landing/)
3.	Click the Install or Get button.
   
## How to Launch the Dashboard

1.	Open the terminal: Find the Command Prompt application.
2.	Navigate to the Folder: Type `cd` followed by the path to the folder where you downloaded this project, then press `Enter`.
3.	Start the Program: Type `jupyter notebook` and press `Enter`.
4.	Open the Dashboard: A new browser window will open automatically. Find and click on the file named `transformer_risk_dashboard_v1.0.0.ipynb` in the file list.
5.	Run the Analysis: Once the file opens, click the `Run` menu at the top of the screen and select `Run All Cells`. The interactive dashboard will appear at the bottom of the page.
 
## Using the Dashboard

Once the dashboard appears, you can use the controls on the left-hand panel.
**Date Window**: Select your desired Start and End dates for the analysis.
** Thresholds**:
-	**Temp Threshold (°F)**: Adjust this to define what constitutes a "hot hour".
-	**Max Load (%)**: Adjust this to define the percentage load at which a transformer is considered at risk.
**Circuit Selector**: Choose one or multiple circuits from the list. 
**Refresh**: After changing any of the above settings, click the Refresh button to update the map with the latest data.
## Important Notes
-	**Manual Refresh**: The dashboard will not always update automatically when you change settings. Always click the Refresh button to fetch and display the updated data.
-	**Database Connectivity**: Because this tool uses a trusted internal database connection, ensure you are connected to the MMLD staff Wi-Fi using an mhdld.com account with database permissions before running the analysis.
-	**Troubleshooting**: If the map does not appear, make sure you have successfully completed the Run All Cells step. If you receive a database error, double-check your network connection.

## To Do

- Add input for hours over limit threshold
- Add display section for current selected inputs for ease of exporting and presentation

