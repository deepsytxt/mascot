@echo off
rem Installs deepsy on Windows: finds (or installs) Python, creates .venv, installs dependencies, builds the icon and shortcuts.
rem Options: --autostart --no-desktop --no-launch --no-deps --uninstall
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
set "PYEXE="
set "PYARG="
set "CODE=0"
echo.
echo  === deepsy installer ===
echo  Folder: %CD%
echo.
if not exist "%~dp0mascot.py" goto notproject
if not exist "%~dp0tools\install.py" goto notproject

call :findpython
if defined PYEXE goto run

echo  Python 3.9 - 3.13 was not found on this computer.
echo  (The "python" entry from the Microsoft Store does not count - it is only a stub.)
echo.
choice /c YN /n /m " Download and install Python 3.12 for your user now? [Y/N] "
if errorlevel 2 goto nopython
call :installpython
call :findpython
if not defined PYEXE goto nopython

:run
echo  Using Python: %PYEXE% %PYARG%
echo.
"%PYEXE%" %PYARG% "%~dp0tools\install.py" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" echo. & echo  The installer stopped with an error, code %CODE%. Read the messages above.
goto finish

:notproject
echo  ERROR: install.bat must stay inside the full project folder, next to mascot.py.
echo  If you opened it from a ZIP archive: right-click the ZIP, choose "Extract All",
echo  then run install.bat from the extracted folder.
set "CODE=1"
goto finish

:nopython
echo.
echo  Python could not be set up automatically.
echo  Install Python 3.12 from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
echo  then run install.bat again.
set "CODE=1"
goto finish

:finish
echo.
echo %cmdcmdline% | find /i "/c" >nul
if not errorlevel 1 pause
exit /b %CODE%

rem ---------------------------------------------------------------

:findpython
set "PYEXE="
set "PYARG="
where py >nul 2>nul
if errorlevel 1 goto findpath
for %%V in (3.13 3.12 3.11 3.10 3.9) do call :trypy %%V
if defined PYEXE exit /b 0
:findpath
for /f "delims=" %%P in ('where python 2^>nul') do call :trypath "%%P"
if defined PYEXE exit /b 0
for %%V in (313 312 311 310 39) do call :trypath "%LocalAppData%\Programs\Python\Python%%V\python.exe"
if defined PYEXE exit /b 0
for %%V in (313 312 311 310 39) do call :trypath "%ProgramFiles%\Python%%V\python.exe"
exit /b 0

:trypy
if defined PYEXE exit /b 0
py -%1 -c "import sys" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE=py"
set "PYARG=-%1"
exit /b 0

:trypath
if defined PYEXE exit /b 0
if not exist %1 exit /b 0
echo %1 | find /i "WindowsApps" >nul
if not errorlevel 1 exit /b 0
%1 -c "import sys;sys.exit(0 if (3,9)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE=%~1"
exit /b 0

:installpython
set "ARCH=amd64"
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=arm64"
set "PYURL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-%ARCH%.exe"
set "PYSETUP=%TEMP%\deepsy-python-setup.exe"
echo.
echo  Downloading Python 3.12 from python.org ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue';[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;Invoke-WebRequest -UseBasicParsing -Uri '%PYURL%' -OutFile '%PYSETUP%'"
if errorlevel 1 echo  Download failed. Check your internet connection. & exit /b 1
if not exist "%PYSETUP%" exit /b 1
echo  Installing Python, this takes about a minute ...
"%PYSETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Shortcuts=0
if errorlevel 1 echo  The Python installer reported an error. & exit /b 1
del "%PYSETUP%" >nul 2>nul
echo  Python installed.
echo.
exit /b 0
