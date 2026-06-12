import os
import socket
import logging
import pyodbc
import psycopg2
import psycopg2.extras
from decimal import Decimal
from datetime import datetime, date

# Logger dedicado para conexiones (no imprime en stdout en cada request).
# Por defecto nivel WARNING: las conexiones exitosas/cierres van a DEBUG y
# quedan silenciadas, evitando ruido y presion sobre el pipe de stdout del servicio.
logger = logging.getLogger("db_conn")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
logger.setLevel(getattr(logging, os.getenv("DB_LOG_LEVEL", "WARNING").upper(), logging.WARNING))

# Habilitar pooling del driver ODBC: reutiliza conexiones fisicas cuando el
# connection string coincide, abaratando el connect por request.
pyodbc.pooling = True


def _int_env(name, default):
    try:
        value = int(os.getenv(name, default))
        return value if value > 0 else int(default)
    except (TypeError, ValueError):
        return int(default)


class SQLServerConnection(object):
    def __init__(self, server, database, username=None, password=None, driver=None, trusted_connection=False):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.driver = driver or "{ODBC Driver 17 for SQL Server}"
        self.trusted_connection = trusted_connection
        self.conn = None
        # Timeouts configurables por entorno (segundos).
        # login_timeout evita que connect() se cuelgue indefinidamente si SQL
        # Server o la red tienen un blip; query_timeout corta queries lentas.
        self.login_timeout = _int_env("DB_LOGIN_TIMEOUT", "5")
        self.query_timeout = _int_env("DB_QUERY_TIMEOUT", "30")
        self.tcp_preflight = os.getenv("DB_TCP_PREFLIGHT", "true").lower() in {"1", "true", "yes"}

    def _tcp_preflight_ok(self):
        """Verifica con un socket (que SI respeta el timeout) que el host:puerto SQL
        este accesible, antes de llamar a pyodbc.connect. Esto evita que un hilo se
        quede colgado ~20s por reintentos TCP cuando el servidor esta inalcanzable
        (caso 'agujero negro' que el login timeout de ODBC no acota en Windows).
        Retorna True si no se puede determinar el puerto (instancia con nombre)."""
        if not self.tcp_preflight or not self.server:
            return True

        server = self.server.strip()
        port = 1433
        if "," in server:                      # formato HOST,PUERTO
            host, _, port_str = server.partition(",")
            try:
                port = int(port_str.strip())
            except ValueError:
                port = 1433
            host = host.strip()
        elif "\\" in server:                   # instancia con nombre: puerto dinamico, no se puede pre-chequear
            return True
        else:
            host = server

        try:
            sock = socket.create_connection((host, port), timeout=self.login_timeout)
            sock.close()
            return True
        except Exception as e:
            logger.warning(f"Pre-chequeo TCP a {host}:{port} fallo en {self.login_timeout}s: {e}")
            return False

    def connect(self):
        try:
            # Fail-fast si el servidor no es alcanzable a nivel TCP.
            if not self._tcp_preflight_ok():
                self.conn = None
                return False
            if self.trusted_connection:
                connection_string = (
                    f"DRIVER={self.driver};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"Trusted_Connection=yes;"
                    f"Connection Timeout={self.login_timeout};"
                )
            else:
                connection_string = (
                    f"DRIVER={self.driver};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"UID={self.username};"
                    f"PWD={self.password};"
                    f"Connection Timeout={self.login_timeout};"
                )

            # timeout= es el login timeout de pyodbc (segundos). Si SQL Server no
            # responde, connect() falla rapido en vez de bloquear el hilo.
            self.conn = pyodbc.connect(connection_string, timeout=self.login_timeout)
            # timeout de operaciones (queries) sobre esta conexion.
            try:
                self.conn.timeout = self.query_timeout
            except Exception:
                pass
            logger.debug("Conexion exitosa a la base de datos SQL Server")
            return True
        except Exception as e:
            logger.warning(f"Error de conexion SQL Server: {e}")
            return False

    def _convert_row_to_dict(self, cursor, row):
        if row is None:
            return None

        columns = [column[0] for column in cursor.description]
        row_dict = {}

        for i, value in enumerate(row):
            column_name = columns[i]
            if isinstance(value, Decimal):
                value = float(value)
            elif isinstance(value, (datetime, date)):
                value = value.isoformat() if value else None
            row_dict[column_name] = value

        return row_dict

    def execute_query(self, query, params=None, fetch_one=False):
        if not self.conn:
            logger.debug("No hay conexion a la base de datos. Intentando reconectar...")
            self.connect()

        try:
            cursor = self.conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if query.strip().upper().startswith("SELECT") or "OUTPUT" in query.upper():
                if fetch_one:
                    row = cursor.fetchone()
                    result = self._convert_row_to_dict(cursor, row)
                    cursor.close()
                    return result
                rows = cursor.fetchall()
                results = [self._convert_row_to_dict(cursor, row) for row in rows]
                cursor.close()
                return results

            self.conn.commit()
            rows_affected = cursor.rowcount
            cursor.close()
            return rows_affected

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error ejecutando la consulta: {str(e)}")
            logger.error(f"Query: {query}")
            logger.error(f"Parametros: {params}")
            raise e

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("Conexion cerrada")


class PostgreSQLConnection(object):
    def __init__(self, dbname, user, password, host, port=5432):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.conn = None
        self.connect_timeout = _int_env("PG_CONNECT_TIMEOUT", "5")

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
                connect_timeout=self.connect_timeout,
            )
            logger.debug("Conexion exitosa a la base de datos PostgreSQL")
            return True
        except Exception as e:
            logger.warning(f"Error de conexion PostgreSQL: {e}")
            return False

    def execute_query(self, query, params=None, fetch_one=False):
        if not self.conn:
            logger.debug("No hay conexion a la base de datos. Intentando reconectar...")
            self.connect()

        try:
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)

            if query.strip().upper().startswith("SELECT") or "RETURNING" in query.upper():
                if fetch_one:
                    result = cursor.fetchone()
                    cursor.close()
                    return result
                results = cursor.fetchall()
                cursor.close()
                return results

            self.conn.commit()
            rows_affected = cursor.rowcount
            cursor.close()
            return rows_affected

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error ejecutando la consulta: {str(e)}")
            logger.error(f"Query: {query}")
            logger.error(f"Parametros: {params}")
            raise e

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("Conexion cerrada")
