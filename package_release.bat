@echo off
setlocal enabledelayedexpansion

rem Release packaging script for end users.
cd /d "%~dp0"

set RELEASE_DIR=%~dp0dist_release
set BUNDLE_DIR=%~dp0dist\export_pipeline
set OUT_ZIP=%~dp0nexgrid_importer_release.zip

if not exist "%BUNDLE_DIR%\export_pipeline.exe" (
  echo ERROR: build output not found in dist\export_pipeline.
  echo Please run build.bat first.
  exit /b 1
)

if exist "%RELEASE_DIR%" (
  echo Removing old release folder...
  rmdir /S /Q "%RELEASE_DIR%"
)

mkdir "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%\incoming"
mkdir "%RELEASE_DIR%\archive"
echo.> "%RELEASE_DIR%\incoming\.gitkeep"
echo.> "%RELEASE_DIR%\archive\.gitkeep"

echo Copying bundle...
xcopy /E /I /Y "%BUNDLE_DIR%" "%RELEASE_DIR%\export_pipeline\" >nul

echo Copying wrapper and documentation...
copy /Y "run_export.bat" "%RELEASE_DIR%\" >nul
copy /Y "README.md" "%RELEASE_DIR%\" >nul

if exist "%OUT_ZIP%" del /Q "%OUT_ZIP%"
echo Creating ZIP archive...
powershell -NoLogo -NoProfile -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%OUT_ZIP%'" >nul

echo Release package created: %OUT_ZIP%
echo Contents:
dir "%RELEASE_DIR%" /B

endlocal
