@echo off
rem Ready Reply for Windows: double-click this file.
setlocal
cd /d "%~dp0"
title Ready Reply

if not exist "readyreply\main.py" goto :not_extracted
if not exist "wheels\" goto :not_extracted

call :find_python
if not defined PY call :install_python
if not defined PY goto :no_python

if not exist ".venv\installed-1.0.0.txt" (
  echo Installing Ready Reply. This happens only the first time...
  %PY% -m venv .venv || goto :failed
  ".venv\Scripts\python.exe" -m pip install --quiet --no-index --find-links wheels -r requirements.txt || ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :failed
  echo ok> ".venv\installed-1.0.0.txt"
)
if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo   Keep this window open while you use Ready Reply. Close it to stop the program.
echo   If Windows asks about the firewall, choose "Allow" on private networks so phones can connect.
".venv\Scripts\python.exe" -m readyreply
pause
exit /b 0

:find_python
set "PY="
for %%V in (3.13 3.12 3.14) do if not defined PY py -%%V -c "import sys" >/dev/null 2>/dev/null && set "PY=py -%%V"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >/dev/null 2>/dev/null && set "PY=python"
for %%V in (313 312) do if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
exit /b 0

:install_python
where winget >/dev/null 2>/dev/null || exit /b 0
echo Python 3.12 is needed. Installing it with winget (this can take a few minutes)...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :find_python
exit /b 0

:not_extracted
echo.
echo   Ready Reply is still inside the zip file.
echo   1. Close this window.
echo   2. Right-click ready-reply-v1.0.0.zip and choose "Extract All", then "Extract".
echo   3. Open the new ready-reply-v1.0.0 folder and double-click start.bat there.
echo.
echo   Ready Reply todavia esta dentro del archivo zip.
echo   1. Cierre esta ventana.
echo   2. Clic derecho sobre ready-reply-v1.0.0.zip, "Extraer todo" y luego "Extraer".
echo   3. Abra la carpeta nueva ready-reply-v1.0.0 y haga doble clic en start.bat ahi.
pause
exit /b 1

:no_python
echo.
echo   Ready Reply needs Python 3.12 or newer.
echo   1. A download page will open. Install Python and tick "Add python.exe to PATH".
echo   2. Then double-click start.bat again.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:failed
echo.
echo   The installation failed. Delete the .venv folder and try again.
echo   If it keeps failing, check the FAQ in README.md.
echo   La instalacion fallo. Borre la carpeta .venv e intente de nuevo.
pause
exit /b 1
