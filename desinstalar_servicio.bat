@echo off
echo ================================================
echo Desinstalador del Servicio API Unificada
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

echo Deteniendo servicio...
python "%~dp0api_service.py" stop

echo.
echo Desinstalando servicio...
python "%~dp0api_service.py" remove

echo.
echo ================================================
echo Servicio desinstalado correctamente!
echo ================================================
echo.
pause
