"""
Script para ejecutar KIROX-FEVRIPS como servicio de Windows.
Usa win32serviceutil para crear un servicio de Windows con:
  - Auto-relanzamiento del proceso uvicorn si muere inesperadamente (backoff).
  - Watchdog interno que vigila /ping y reinicia uvicorn si la API queda colgada.

Instalacion:
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
import ssl
import sys
import os
import subprocess
import threading
import logging
import urllib.request
from logging.handlers import TimedRotatingFileHandler

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


class KiroxFevripsService(win32serviceutil.ServiceFramework):
    _svc_name_ = "KiroxFevrips"
    _svc_display_name_ = "KIROX-FEVRIPS - Hospital Sagrado Corazon de Jesus"
    _svc_description_ = ("API unificada RIPS (consulta Odoo + envio CAPITA + envio automatico EVENTO) "
                         "con auto-reinicio y watchdog de salud.")

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
        self.watchdog_thread = None
        self._uses_ssl = False
        # Configuracion de resiliencia (por entorno)
        self.restart_backoff = _int_env("SERVICE_RESTART_BACKOFF", 3)      # seg entre reintentos
        self.restart_backoff_max = _int_env("SERVICE_RESTART_BACKOFF_MAX", 30)
        self.watchdog_enabled = os.getenv("WATCHDOG_ENABLED", "true").lower() in {"1", "true", "yes"}
        self.watchdog_interval = _int_env("WATCHDOG_INTERVAL", 30)         # seg entre sondas
        self.watchdog_timeout = _int_env("WATCHDOG_TIMEOUT", 5)            # seg de timeout por sonda
        self.watchdog_fails = _int_env("WATCHDOG_FAILS", 3)               # fallos seguidos -> reinicio
        self.watchdog_grace = _int_env("WATCHDOG_GRACE", 30)              # seg de gracia tras arrancar

    # ------------------------------------------------------------------ logging
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

    # ------------------------------------------------------------------ stop
    def SvcStop(self):
        """Detener el servicio"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, 'Deteniendo KIROX-FEVRIPS...')
        )

        self.is_alive = False
        win32event.SetEvent(self.hWaitStop)
        self._kill_process()

        if self.watchdog_thread and self.watchdog_thread.is_alive():
            self.watchdog_thread.join(timeout=5)

        self._join_output_threads()
        self._close_logger(self.stdout_logger)
        self._close_logger(self.stderr_logger)
        self.stdout_logger = None
        self.stderr_logger = None

    def _kill_process(self):
        """Termina el proceso uvicorn actual de forma segura."""
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def _join_output_threads(self):
        if self.stdout_thread and self.stdout_thread.is_alive():
            self.stdout_thread.join(timeout=5)
        if self.stderr_thread and self.stderr_thread.is_alive():
            self.stderr_thread.join(timeout=5)
        self.stdout_thread = None
        self.stderr_thread = None

    # ------------------------------------------------------------------ run
    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, 'KIROX-FEVRIPS iniciado')
        )
        self.main()

    def _build_cmd(self, script_dir, python_exe):
        """Construye el comando de uvicorn (con SSL si hay certificados)."""
        cmd = [
            python_exe,
            "-m", "uvicorn",
            "api:app",
            "--host", os.getenv("API_HOST", "0.0.0.0"),
            "--port", str(_int_env("API_PORT", 8000)),
            "--no-access-log"
        ]
        cert_file = os.path.join(script_dir, "certs", "server.crt")
        key_file = os.path.join(script_dir, "certs", "server.key")
        if os.path.exists(cert_file) and os.path.exists(key_file):
            cmd.extend(["--ssl-certfile", cert_file, "--ssl-keyfile", key_file])
            self._uses_ssl = True
        else:
            self._uses_ssl = False
        return cmd

    def _launch_uvicorn(self, cmd, script_dir):
        """Lanza uvicorn como subproceso y engancha los hilos de logging."""
        # Forzar UTF-8 en el hijo: leemos su stdout/stderr como UTF-8 (encoding="utf-8"), pero
        # por defecto en Windows el proceso hijo escribe en cp1252, lo que producía mojibake en
        # los logs (p.ej. "validaci�n", "facturaci�n"). PYTHONUTF8/PYTHONIOENCODING alinean la
        # codificación de salida del hijo con la lectura del padre.
        child_env = os.environ.copy()
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=script_dir,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=child_env
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

    def _ping_url(self):
        host = os.getenv("API_HOST", "0.0.0.0")
        # 0.0.0.0 no es direccionable como cliente; usar loopback
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        scheme = "https" if self._uses_ssl else "http"
        return f"{scheme}://{host}:{_int_env('API_PORT', 8000)}/ping"

    def _watchdog_loop(self):
        """Vigila /ping; si falla N veces seguidas, mata uvicorn (el loop principal lo relanza)."""
        url = self._ping_url()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # Periodo de gracia inicial para no reiniciar durante el arranque
        if win32event.WaitForSingleObject(self.hWaitStop, self.watchdog_grace * 1000) == win32event.WAIT_OBJECT_0:
            return

        fails = 0
        while self.is_alive:
            # Solo sondear si el proceso esta vivo
            if self.process and self.process.poll() is None:
                ok = False
                try:
                    with urllib.request.urlopen(url, timeout=self.watchdog_timeout, context=ctx) as resp:
                        ok = (resp.status == 200)
                except Exception:
                    ok = False

                if ok:
                    fails = 0
                else:
                    fails += 1
                    servicemanager.LogErrorMsg(
                        f"[WATCHDOG] /ping sin respuesta ({fails}/{self.watchdog_fails}) en {url}"
                    )
                    if fails >= self.watchdog_fails:
                        servicemanager.LogErrorMsg(
                            "[WATCHDOG] API colgada: reiniciando proceso uvicorn..."
                        )
                        self._kill_process()  # el loop principal detecta la muerte y relanza
                        fails = 0
                        # Esperar gracia tras el reinicio forzado
                        if win32event.WaitForSingleObject(self.hWaitStop, self.watchdog_grace * 1000) == win32event.WAIT_OBJECT_0:
                            return

            if win32event.WaitForSingleObject(self.hWaitStop, self.watchdog_interval * 1000) == win32event.WAIT_OBJECT_0:
                return

    def main(self):
        """Logica principal: supervisa uvicorn y lo relanza si muere o se cuelga."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            os.chdir(script_dir)

            from dotenv import load_dotenv
            load_dotenv()

            # Python del venv si existe
            venv_python = os.path.join(script_dir, "venv", "Scripts", "python.exe")
            python_exe = venv_python if os.path.exists(venv_python) else sys.executable

            cmd = self._build_cmd(script_dir, python_exe)

            log_dir = os.path.join(script_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            self.stdout_logger = self._build_rotating_logger(
                "api_service_stdout", os.path.join(log_dir, "api_service_stdout.log"))
            self.stderr_logger = self._build_rotating_logger(
                "api_service_stderr", os.path.join(log_dir, "api_service_stderr.log"))

            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, f'Iniciando API desde: {script_dir} ({"HTTPS" if self._uses_ssl else "HTTP"})')
            )

            # Lanzar uvicorn por primera vez
            self._launch_uvicorn(cmd, script_dir)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, f'API corriendo en {os.getenv("API_HOST", "0.0.0.0")}:{_int_env("API_PORT", 8000)}')
            )

            # Watchdog
            if self.watchdog_enabled:
                self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
                self.watchdog_thread.start()

            current_backoff = self.restart_backoff

            # Bucle de supervision
            while self.is_alive:
                if self.process.poll() is not None:
                    # El proceso termino: si fue por parada del servicio, salir
                    if not self.is_alive:
                        break

                    returncode = self.process.returncode
                    servicemanager.LogErrorMsg(
                        f"uvicorn termino inesperadamente (codigo {returncode}). "
                        f"Reintentando en {current_backoff}s. Logs: logs\\api_service_*.log"
                    )

                    # Limpiar hilos de salida del proceso muerto
                    self._join_output_threads()

                    # Esperar backoff (interrumpible por stop)
                    if win32event.WaitForSingleObject(self.hWaitStop, current_backoff * 1000) == win32event.WAIT_OBJECT_0:
                        break
                    if not self.is_alive:
                        break

                    # Relanzar
                    try:
                        self._launch_uvicorn(cmd, script_dir)
                        servicemanager.LogMsg(
                            servicemanager.EVENTLOG_INFORMATION_TYPE,
                            servicemanager.PYS_SERVICE_STARTED,
                            (self._svc_name_, 'uvicorn relanzado por el supervisor')
                        )
                        # backoff exponencial acotado para evitar crash-loops agresivos
                        current_backoff = min(current_backoff * 2, self.restart_backoff_max)
                    except Exception as relaunch_error:
                        servicemanager.LogErrorMsg(f"Error relanzando uvicorn: {relaunch_error}")
                        current_backoff = min(current_backoff * 2, self.restart_backoff_max)
                else:
                    # Proceso sano: resetear backoff
                    current_backoff = self.restart_backoff

                # Verificar cada segundo / responder al stop
                if win32event.WaitForSingleObject(self.hWaitStop, 1000) == win32event.WAIT_OBJECT_0:
                    break

        except Exception as e:
            servicemanager.LogErrorMsg(f"Error en servicio KIROX-FEVRIPS: {e}")
            import traceback
            servicemanager.LogErrorMsg(traceback.format_exc())
        finally:
            self._kill_process()
            self._join_output_threads()
            self._close_logger(self.stdout_logger)
            self._close_logger(self.stderr_logger)
            self.stdout_logger = None
            self.stderr_logger = None


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(KiroxFevripsService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(KiroxFevripsService)
