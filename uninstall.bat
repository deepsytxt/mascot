@echo off
rem Removes shortcuts, autostart and .venv (settings in %APPDATA%\deepsy are kept).
call "%~dp0install.bat" --uninstall %*
