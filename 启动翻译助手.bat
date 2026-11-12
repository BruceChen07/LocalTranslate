@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo     译心 . 本地翻译助手
echo ============================================
echo.
py -3.12 -c "import streamlit" >nul 2>nul
if errorlevel 1 goto use_python
py -3.12 launcher.py
goto after
:use_python
python launcher.py
:after
if errorlevel 1 pause
