@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

set "TARGET=C:\temp\html"
if not "%~1"=="" set "TARGET=%~1"

echo === HTML migration and template update ===
echo.
echo Target: %TARGET%
echo.
echo Actions:
echo   1. Convert legacy HTML folders to data.js + index.html.
echo   2. Update index.html in all migrated folders.
echo.
echo Legacy HTML files are preserved as .html.bak files.
echo.

if exist "%TARGET%\" goto target_ok
echo [ERROR] Target folder does not exist: %TARGET%
pause
exit /b 1

:target_ok
pause

".venv\Scripts\python.exe" --version >nul 2>&1
if not errorlevel 1 goto run_venv

echo.
echo [ERROR] The required .venv Python environment is missing or unusable.
echo Run setup.bat before running this file.
pause
exit /b 1

:run_venv
echo Runtime: .venv
".venv\Scripts\python.exe" ret_youyaku_html.py --migrate "%TARGET%"
goto finished

:finished
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" goto failed
echo Migration and template update completed.
pause
exit /b 0

:failed
echo [ERROR] Migration or update failed. Exit code: %RESULT%
pause
exit /b %RESULT%
