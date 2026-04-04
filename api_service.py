"""
Script para ejecutar la API Unificada como servicio de Windows.
Este script usa win32serviceutil para crear un servicio de Windows.

Instalación:
    python api_service.py install

Iniciar servicio:
    python api_service.py start

Detener servicio:
    python api_service.py stop

Remover servicio:
    python api_service.py remove
"""

import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os
import subprocess
import time
import threading
import logging
from logging.handlers import TimedRotatingFileHandler

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class APIUnificadaService(win32serviceutil.ServiceFramework):
    _svc_name_ = "APIUnificadaHospital"
    _svc_display_name_ = "API Unificada - Hospital Sagrado Corazón de Jesús"
    _svc_description_ = "API REST para exposición de datos RIPS y envío de facturas CAPITA al Ministerio de Salud"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_alive = True
        self.process = None
        self.stdout_thread = None
        self.stderr_thread = None
        self.stdout_logger = None
        self.stderr_logger = None

    def _build_rotating_logger(self, logger_name, log_file_path):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

        file_handler = TimedRotatingFileHandler(
            log_file_path,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(file_handler)
        return logger

    def _close_logger(self, logger):
        if not logger:
            return

        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    def _stream_subprocess_output(self, stream, logger, level):
        try:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                logger.log(level, line.rstrip())
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error leyendo salida del subproceso: {e}")
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def SvcStop(self):
        """Detener el servicio"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, 'Deteniendo API Unificada...')
        )
        
        # Terminar el proceso de uvicorn
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except:
                self.process.kill()

        if self.stdout_thread and self.stdout_thread.is_alive():
            self.stdout_thread.join(timeout=5)
        if self.stderr_thread and self.stderr_thread.is_alive():
            self.stderr_thread.join(timeout=5)

        self.stdout_thread = None
        self.stderr_thread = None
        self._close_logger(self.stdout_logger)
        self._close_logger(self.stderr_logger)
        self.stdout_logger = None
        self.stderr_logger = None
        
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False

    def SvcDoRun(self):
        """Ejecutar el servicio"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, 'API Unificada iniciada')
        )
        self.main()

    def main(self):
        """Lógica principal del servicio"""
        try:
            # Obtener la ruta del directorio del script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Cambiar al directorio del script
            os.chdir(script_dir)
            
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, f'Iniciando API desde: {script_dir}')
            )
            
            # Importar configuración para obtener host y puerto
            from dotenv import load_dotenv; import os; load_dotenv()
            
            # Usar Python del entorno virtual si existe
            venv_python = os.path.join(script_dir, "venv", "Scripts", "python.exe")
            if os.path.exists(venv_python):
                python_exe = venv_python
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, f'Usando Python del venv: {venv_python}')
                )
            else:
                python_exe = sys.executable
            
            # Iniciar uvicorn como subproceso
            cmd = [
                python_exe,
                "-m", "uvicorn",
                "api:app",
                "--host", os.getenv("API_HOST", "0.0.0.0"),
                "--port", str(int(os.getenv("API_PORT", "8000"))),
                "--no-access-log"
            ]
            
            # Verificar si existen certificados SSL
            cert_file = os.path.join(script_dir, "certs", "server.crt")
            key_file = os.path.join(script_dir, "certs", "server.key")
            
            if os.path.exists(cert_file) and os.path.exists(key_file):
                cmd.extend([
                    "--ssl-certfile", cert_file,
                    "--ssl-keyfile", key_file
                ])
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STARTED,
                    (self._svc_name_, 'Iniciando con HTTPS (SSL/TLS)')
                )

            # Evita bloqueos del servicio por buffers llenos cuando hay mucha salida.
            log_dir = os.path.join(script_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            self.stdout_logger = self._build_rotating_logger(
                "api_service_stdout",
                os.path.join(log_dir, "api_service_stdout.log")
            )
            self.stderr_logger = self._build_rotating_logger(
                "api_service_stderr",
                os.path.join(log_dir, "api_service_stderr.log")
            )
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=script_dir,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )

            self.stdout_thread = threading.Thread(
                target=self._stream_subprocess_output,
                args=(self.process.stdout, self.stdout_logger, logging.INFO),
                daemon=True
            )
            self.stderr_thread = threading.Thread(
                target=self._stream_subprocess_output,
                args=(self.process.stderr, self.stderr_logger, logging.ERROR),
                daemon=True
            )
            self.stdout_thread.start()
            self.stderr_thread.start()
            
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, f'API corriendo en {os.getenv("API_HOST", "0.0.0.0")}:{int(os.getenv("API_PORT", "8000"))}')
            )
            
            # Esperar a que se detenga el servicio
            while self.is_alive:
                # Verificar si el proceso sigue corriendo
                if self.process.poll() is not None:
                    # El proceso terminó inesperadamente
                    error_msg = f"API Unificada terminó inesperadamente. Código: {self.process.returncode}"
                    error_msg += "\nRevisar logs: logs\\api_service_stdout.log* y logs\\api_service_stderr.log*"
                    servicemanager.LogErrorMsg(error_msg)
                    break
                
                # Esperar un segundo antes de verificar nuevamente
                rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
                if rc == win32event.WAIT_OBJECT_0:
                    break
            
        except Exception as e:
            servicemanager.LogErrorMsg(f"Error en servicio API Unificada: {e}")
            import traceback
            servicemanager.LogErrorMsg(traceback.format_exc())
        finally:
            if self.stdout_thread and self.stdout_thread.is_alive():
                self.stdout_thread.join(timeout=5)
            if self.stderr_thread and self.stderr_thread.is_alive():
                self.stderr_thread.join(timeout=5)

            self._close_logger(self.stdout_logger)
            self._close_logger(self.stderr_logger)
            self.stdout_logger = None
            self.stderr_logger = None
            self.stdout_thread = None
            self.stderr_thread = None


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(APIUnificadaService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(APIUnificadaService)
