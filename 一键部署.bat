@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo     译心 . 部署（下载引擎与模型）
echo ============================================
echo.
py -3.12 deploy.py %*
if not errorlevel 9009 goto checkfail
python deploy.py %*
:checkfail
if errorlevel 1 goto fail
goto end

:fail
echo.
echo 部署失败，请查看上方提示或 README.md。
pause

:end
