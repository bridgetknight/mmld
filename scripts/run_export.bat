@echo off
setlocal enabledelayedexpansion

rem Base directories
set SCRIPT_DIR=%~dp0
set INCOMING_DIR=%SCRIPT_DIR%incoming
set ARCHIVE_DIR=%SCRIPT_DIR%archive
set BUNDLE_EXE=%SCRIPT_DIR%export_pipeline.exe
set PYTHON_SCRIPT=

if not exist "%INCOMING_DIR%" (
    if exist "%SCRIPT_DIR%nexgrid_reports" (
        set "INCOMING_DIR=%SCRIPT_DIR%nexgrid_reports"
    ) else (
        mkdir "%INCOMING_DIR%"
    )
)
if not exist "%ARCHIVE_DIR%" mkdir "%ARCHIVE_DIR%"

if not exist "%BUNDLE_EXE%" set "BUNDLE_EXE=%SCRIPT_DIR%..\dist\export_pipeline.exe"
if exist "%SCRIPT_DIR%src\export_pipeline.py" (
    set "PYTHON_SCRIPT=%SCRIPT_DIR%src\export_pipeline.py"
) else if exist "%SCRIPT_DIR%..\src\export_pipeline.py" (
    set "PYTHON_SCRIPT=%SCRIPT_DIR%..\src\export_pipeline.py"
)

rem Prefer a bundled export_pipeline.exe if present; otherwise use the Python launcher
rem If a single-file EXE is included, it will be called directly. Otherwise the script uses `py -3`.

if "%~1"=="" (
    echo No file argument provided. Processing all CSVs in %INCOMING_DIR%...
    for %%F in ("%INCOMING_DIR%\*.csv") do (
        echo.
        echo Processing %%~nxF...
        if exist "%BUNDLE_EXE%" (
            "%BUNDLE_EXE%" "%%~fF"
        ) else if defined PYTHON_SCRIPT (
            py -3 "%PYTHON_SCRIPT%" "%%~fF"
        ) else (
            echo ERROR: no bundled export_pipeline.exe or Python source found
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
if exist "%BUNDLE_EXE%" (
    "%BUNDLE_EXE%" "%CSV_PATH%"
) else if defined PYTHON_SCRIPT (
    py -3 "%PYTHON_SCRIPT%" "%CSV_PATH%"
) else (
    echo ERROR: no bundled export_pipeline.exe or Python source found
    goto end
)
if errorlevel 1 (
    echo ERROR: processing %CSV_PATH%
    goto end
)
move /Y "%CSV_PATH%" "%ARCHIVE_DIR%\" >nul
echo Archived %CSV_PATH%

:end
endlocal
