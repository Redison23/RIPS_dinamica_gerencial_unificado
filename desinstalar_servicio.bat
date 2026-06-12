@echo off
echo ================================================
echo Desinstalador del Servicio KIROX-FEVRIPS
echo Hospital Sagrado Corazon de Jesus de Quimbaya
echo ================================================
echo.

REM Verificar si se esta ejecutando como administrador
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Este script debe ejecutarse como Administrador
    echo Por favor, haz clic derecho y selecciona "Ejecutar como administrador"
    pause
    exit /b 1
)

REM Cambiar al directorio del script
cd /d "%~dp0"
echo Directorio actual: %CD%
echo.

REM Usar el Python del venv si existe
set "PYEXE=python"
if exist "%~dp0venv\Scripts\python.exe" set "PYEXE=%~dp0venv\Scripts\python.exe"

echo Deteniendo servicio...
"%PYEXE%" "%~dp0api_service.py" stop

echo.
echo Desinstalando servicio...
"%PYEXE%" "%~dp0api_service.py" remove

echo.
echo ================================================
echo Servicio KIROX-FEVRIPS desinstalado correctamente!
echo ================================================
echo.
pause
