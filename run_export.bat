@echo off
setlocal enabledelayedexpansion

rem Base directories
set SCRIPT_DIR=%~dp0
set INCOMING_DIR=%SCRIPT_DIR%nexgrid_hourly_reports_monthly
set ARCHIVE_DIR=%SCRIPT_DIR%archive

if not exist "%ARCHIVE_DIR%" mkdir "%ARCHIVE_DIR%"

rem Prefer a bundled export_pipeline.exe if present; otherwise use the Python launcher
rem If a single-file EXE is included, it will be called directly. Otherwise the script uses `py -3`.

if "%~1"=="" (
    echo No file argument provided. Processing all CSVs in %INCOMING_DIR%...
    for %%F in ("%INCOMING_DIR%\*.csv") do (
        echo.
        echo Processing %%~nxF...
        if exist "%SCRIPT_DIR%export_pipeline.exe" (
            "%SCRIPT_DIR%export_pipeline.exe" "%%~fF"
        ) else (
            py -3 "%SCRIPT_DIR%export_pipeline.py" "%%~fF"
        )
        if errorlevel 1 (
            echo ERROR: processing %%~nxF
        ) else (
            move /Y "%%~fF" "%ARCHIVE_DIR%\" >nul
            echo Archived %%~nxF
        )
    )
    goto end
)

set INPUT=%~1
if exist "%INPUT%" (
    set CSV_PATH=%INPUT%
) else (
    set CSV_PATH=%INCOMING_DIR%\%INPUT%
)

if /I not "%CSV_PATH:~-4%"==".csv" (
    echo Error: input must be a .csv file
    goto end
)

if not exist "%CSV_PATH%" (
    echo Error: file not found: %CSV_PATH%
    goto end
)

echo Processing %CSV_PATH%...
if exist "%SCRIPT_DIR%export_pipeline.exe" (
    "%SCRIPT_DIR%export_pipeline.exe" "%CSV_PATH%"
) else (
    py -3 "%SCRIPT_DIR%export_pipeline.py" "%CSV_PATH%"
)
if errorlevel 1 (
    echo ERROR: processing %CSV_PATH%
    goto end
)
move /Y "%CSV_PATH%" "%ARCHIVE_DIR%\" >nul
echo Archived %CSV_PATH%

:end
endlocal
