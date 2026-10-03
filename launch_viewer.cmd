@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "VIEWER_PYTHON=%DROPLET_VISION_PYTHON%"
if not defined VIEWER_PYTHON if exist "configs\viewer.local.txt" set /p "VIEWER_PYTHON=" < "configs\viewer.local.txt"
if not defined VIEWER_PYTHON if exist "VisionLab\Scripts\python.exe" set "VIEWER_PYTHON=%CD%\VisionLab\Scripts\python.exe"
if not defined VIEWER_PYTHON if defined VIRTUAL_ENV set "VIEWER_PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
if not defined VIEWER_PYTHON goto missing_python
if not exist "%VIEWER_PYTHON%" goto missing_python
"%VIEWER_PYTHON%" "scripts\launch_viewer.py" %*
set "VIEWER_EXIT=%ERRORLEVEL%"
if not "%VIEWER_EXIT%"=="0" pause
exit /b %VIEWER_EXIT%

:missing_python
echo VisionLab Python was not found. No packages have been installed.
echo Put its python.exe path in configs\viewer.local.txt or set DROPLET_VISION_PYTHON.
echo Alternatively create VisionLab in this repository, or activate it first.
pause
exit /b 1
