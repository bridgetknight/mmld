@echo off
setlocal enabledelayedexpansion

rem Base directories
set SCRIPT_DIR=%~dp0
set INCOMING_DIR=%SCRIPT_DIR%incoming
set ARCHIVE_DIR=%SCRIPT_DIR%archive
set BUNDLE_EXE=
set PYTHON_SCRIPT=

if not exist "%INCOMING_DIR%" (
    if exist "%SCRIPT_DIR%nexgrid_reports" (
        set "INCOMING_DIR=%SCRIPT_DIR%nexgrid_reports"
    ) else (
        mkdir "%INCOMING_DIR%"
    )
)
if not exist "%ARCHIVE_DIR%" mkdir "%ARCHIVE_DIR%"

if exist "%SCRIPT_DIR%export_pipeline.exe" (
    set "BUNDLE_EXE=%SCRIPT_DIR%export_pipeline.exe"
) else if exist "%SCRIPT_DIR%..\dist\export_pipeline\export_pipeline.exe" (
    set "BUNDLE_EXE=%SCRIPT_DIR%..\dist\export_pipeline\export_pipeline.exe"
)
if exist "%SCRIPT_DIR%src\export_pipeline.py" (
    set "PYTHON_SCRIPT=%SCRIPT_DIR%src\export_pipeline.py"
) else if exist "%SCRIPT_DIR%..\src\export_pipeline.py" (
    set "PYTHON_SCRIPT=%SCRIPT_DIR%..\src\export_pipeline.py"
)

rem Prefer a bundled export_pipeline.exe if present; otherwise use the Python launcher
rem If a single-file EXE is included, it will be called directly. Otherwise the script uses the first available Python command.

set PYTHON_CMD=
where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py -3
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set PYTHON_CMD=python
    ) else (
        where python3 >nul 2>&1
        if not errorlevel 1 (
            set PYTHON_CMD=python3
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo Error: No Python launcher found. Install Python or add python to PATH.
    goto end
)

if "%~1"=="" (
    set PROCESS_ALL=1
) else if "%~1"=="." (
    set PROCESS_ALL=1
) else (
    set PROCESS_ALL=0
)

if "%PROCESS_ALL%"=="1" (
    echo Processing all CSVs in %INCOMING_DIR%...
    for %%F in ("%INCOMING_DIR%\*.csv") do (
        echo.
        echo Processing %%~nxF...
        if exist "%BUNDLE_EXE%" (
            "%BUNDLE_EXE%" "%%~fF"
        ) else if defined PYTHON_SCRIPT (
            py -3 "%PYTHON_SCRIPT%" "%%~fF"
        ) else (
            call %PYTHON_CMD% "%SCRIPT_DIR%export_pipeline.py" "%%~fF"
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

for %%A in (%*) do (
    set INPUT=%%~A
    if "!INPUT!"=="." (
        echo Processing all CSVs in %INCOMING_DIR%...
        for %%F in ("%INCOMING_DIR%\*.csv") do (
            echo.
            echo Processing %%~nxF...
            if defined BUNDLE_EXE (
                "%BUNDLE_EXE%" "%%~fF"
            ) else if defined PYTHON_SCRIPT (
                call %PYTHON_CMD% "%PYTHON_SCRIPT%" "%%~fF"
            ) else (
                call %PYTHON_CMD% "%SCRIPT_DIR%export_pipeline.py" "%%~fF"
            )
            if errorlevel 1 (
                echo ERROR: processing %%~nxF
            ) else (
                move /Y "%%~fF" "%ARCHIVE_DIR%\" >nul
                echo Archived %%~nxF
            )
        )
    ) else (
        if exist "!INPUT!" (
            set CSV_PATH=!INPUT!
        ) else if exist "%INCOMING_DIR%\!INPUT!" (
            set CSV_PATH=%INCOMING_DIR%\!INPUT!
        ) else (
            echo Error: file or folder not found: !INPUT!
            goto end
        )

        if exist "!CSV_PATH!\*" (
            echo Processing all CSVs in !CSV_PATH!...
            for %%F in ("!CSV_PATH!\*.csv") do (
                echo.
                echo Processing %%~nxF...
                if defined BUNDLE_EXE (
                    "%BUNDLE_EXE%" "%%~fF"
                ) else if defined PYTHON_SCRIPT (
                    call %PYTHON_CMD% "%PYTHON_SCRIPT%" "%%~fF"
                ) else (
                    call %PYTHON_CMD% "%SCRIPT_DIR%export_pipeline.py" "%%~fF"
                )
                if errorlevel 1 (
                    echo ERROR: processing %%~nxF
                ) else (
                    move /Y "%%~fF" "%ARCHIVE_DIR%\" >nul
                    echo Archived %%~nxF
                )
            )
        ) else if /I "!CSV_PATH:~-4!"==".csv" (
            echo Processing !CSV_PATH!...
            if defined BUNDLE_EXE (
                "%BUNDLE_EXE%" "!CSV_PATH!"
            ) else if defined PYTHON_SCRIPT (
                call %PYTHON_CMD% "%PYTHON_SCRIPT%" "!CSV_PATH!"
            ) else (
                call %PYTHON_CMD% "%SCRIPT_DIR%export_pipeline.py" "!CSV_PATH!"
            )
            if errorlevel 1 (
                echo ERROR: processing !CSV_PATH!
                goto end
            )
            move /Y "!CSV_PATH!" "%ARCHIVE_DIR%\" >nul
            echo Archived !CSV_PATH!
        ) else (
            echo Error: input must be a .csv file or a folder containing .csv files
            goto end
        )
    )
)

:end
endlocal
