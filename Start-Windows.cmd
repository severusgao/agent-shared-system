@echo off
setlocal
set "ASS_SETUP=%~dp0scripts\setup.py"
set "ASS_PYTHON=%USERPROFILE%\.local\share\agent-shared-system\venv\Scripts\python.exe"
if exist "%ASS_PYTHON%" goto run_local
where py >nul 2>nul
if not errorlevel 1 goto run_py
where python >nul 2>nul
if not errorlevel 1 goto run_python
echo Install Python 3.12+ in this system, then run this launcher again.
pause
exit /b 1
:run_local
"%ASS_PYTHON%" -X utf8 -B "%ASS_SETUP%" --interactive
goto finish
:run_py
py -3 -X utf8 -B "%ASS_SETUP%" --interactive
goto finish
:run_python
python -X utf8 -B "%ASS_SETUP%" --interactive
:finish
set "ASS_EXIT=%ERRORLEVEL%"
pause
exit /b %ASS_EXIT%
