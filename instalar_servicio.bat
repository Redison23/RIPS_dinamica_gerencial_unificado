@echo off
echo ============================================
echo Instalador del Servicio API Unificada
echo Hospital Sagrado Corazon de Jesus de Quimbaya
echo ============================================
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

echo Instalando paquete pywin32...
python -m pip install pywin32

echo.
echo Instalando servicio...
python "%~dp0api_service.py" install

echo.
echo Configurando servicio para inicio automatico...
sc config APIUnificadaHospital start= auto

echo.
echo Iniciando servicio...
python "%~dp0api_service.py" start

echo.
echo ============================================
echo Servicio instalado correctamente!
echo ============================================
echo.
echo El servicio "API Unificada - Hospital Sagrado Corazon de Jesus" ahora:
echo - Estara disponible 24/7
echo - Se iniciara automaticamente al reiniciar el PC
echo - Puede ser administrado desde services.msc
echo.
echo Para verificar el estado:
echo   python api_service.py
echo.
echo Para detener el servicio:
echo   python api_service.py stop
echo.
echo Para reiniciar el servicio:
echo   python api_service.py restart
echo.
pause
