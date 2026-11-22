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
echo Using Python: %PY%

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

rem Finds Python 3.12 or newer: the py launcher, PATH, and the usual install folders
rem (so it works even when "Add python.exe to PATH" was not ticked).
:find_python
set "PY="
call :try_python py -3
if not defined PY call :try_python python
if not defined PY call :try_python python3
for %%V in (3.13 3.12 3.14 3.15) do if not defined PY call :try_python py -%%V
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%LOCALAPPDATA%\Python\pythoncore-3*" "%ProgramFiles%\Python3*" "%SystemDrive%\Python3*") do if not defined PY if exist "%%~D\python.exe" call :try_python "%%~D\python.exe"
exit /b 0

:try_python
rem Empty input: if a Python installer offers to download a missing version, it gets "no".
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" <nul >nul 2>nul && set PY=%*
exit /b 0

:install_python
where winget >nul 2>nul || exit /b 0
echo Python 3.12 or newer was not found. Installing Python 3.13 with winget (a few minutes)...
echo No se encontro Python 3.12 o mas nuevo. Instalando Python 3.13 con winget (unos minutos)...
winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
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
echo   Ready Reply needs Python 3.12 or newer and could not find it.
echo   Ready Reply necesita Python 3.12 o mas nuevo y no lo encontro.
echo.
echo   Python versions found on this computer / Versiones de Python encontradas:
py --list 2>nul
where python 2>nul
echo.
echo   1. Install Python from the page that opens. On the first screen, tick "Add python.exe to PATH".
echo      Instale Python desde la pagina que se abre. En la primera pantalla marque "Add python.exe to PATH".
echo   2. Close this window and double-click start.bat again.
echo      Cierre esta ventana y vuelva a hacer doble clic en start.bat.
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
