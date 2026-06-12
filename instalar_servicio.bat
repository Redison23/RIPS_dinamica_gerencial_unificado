@echo off
echo ============================================
echo Instalador del Servicio KIROX-FEVRIPS
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

REM Usar el Python del venv si existe (rutas relativas a este .bat)
set "PYEXE=python"
if exist "%~dp0venv\Scripts\python.exe" set "PYEXE=%~dp0venv\Scripts\python.exe"
echo Usando Python: %PYEXE%
echo.

echo Instalando paquete pywin32...
"%PYEXE%" -m pip install pywin32

echo.
echo Instalando servicio...
"%PYEXE%" "%~dp0api_service.py" install

echo.
echo Corrigiendo host del servicio (pythonservice.exe del venv no resuelve pywin32)...
REM El pythonservice.exe del venv falla con "No module named servicemanager".
REM Usamos el del Python base (que tiene pywin32) + PYTHONPATH al proyecto.
for /f "delims=" %%i in ('"%PYEXE%" -c "import sys,os;p=os.path.join(sys.base_prefix,'pythonservice.exe');q=os.path.join(sys.base_prefix,'Lib','site-packages','win32','pythonservice.exe');print(p if os.path.exists(p) else q)"') do set "SVCEXE=%%i"
echo   pythonservice base: %SVCEXE%
sc config KiroxFevrips binPath= "\"%SVCEXE%\""
reg add "HKLM\SYSTEM\CurrentControlSet\Services\KiroxFevrips" /v Environment /t REG_MULTI_SZ /d "PYTHONPATH=%CD%" /f

echo.
echo Configurando servicio para inicio automatico...
sc config KiroxFevrips start= auto

echo.
echo Configurando recuperacion automatica (reinicio ante fallos)...
sc failure KiroxFevrips reset= 86400 actions= restart/5000/restart/10000/restart/30000
sc failureflag KiroxFevrips 1

echo.
echo Iniciando servicio...
"%PYEXE%" "%~dp0api_service.py" start

echo.
echo ============================================
echo Servicio KIROX-FEVRIPS instalado correctamente!
echo ============================================
echo.
echo El servicio "KIROX-FEVRIPS - Hospital Sagrado Corazon de Jesus" ahora:
echo - Estara disponible 24/7
echo - Se iniciara automaticamente al reiniciar el PC
echo - Se reiniciara solo si el proceso falla (Windows Recovery)
echo - Tiene watchdog interno que reinicia uvicorn si la API se cuelga
echo - Puede ser administrado desde services.msc
echo.
echo Para verificar el estado:
echo   "%PYEXE%" api_service.py
echo.
echo Para detener el servicio:
echo   "%PYEXE%" api_service.py stop
echo.
echo Para reiniciar el servicio:
echo   "%PYEXE%" api_service.py restart
echo.
pause
