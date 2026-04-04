import pyodbc
import psycopg2
import psycopg2.extras
from decimal import Decimal
from datetime import datetime, date


class SQLServerConnection(object):
    def __init__(self, server, database, username=None, password=None, driver=None, trusted_connection=False):
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.driver = driver or "{ODBC Driver 17 for SQL Server}"
        self.trusted_connection = trusted_connection
        self.conn = None

    def connect(self):
        try:
            if self.trusted_connection:
                connection_string = (
                    f"DRIVER={self.driver};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"Trusted_Connection=yes;"
                )
            else:
                connection_string = (
                    f"DRIVER={self.driver};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"UID={self.username};"
                    f"PWD={self.password};"
                )

            self.conn = pyodbc.connect(connection_string)
            print("Conexion exitosa a la base de datos SQL Server")
            return True
        except Exception as e:
            print(f"Error de conexion: {e}")
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
            print("No hay conexion a la base de datos. Intentando reconectar...")
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
            print(f"Error ejecutando la consulta: {str(e)}")
            print(f"Query: {query}")
            print(f"Parametros: {params}")
            raise e

    def close(self):
        if self.conn:
            self.conn.close()
            print("Conexion cerrada")


class PostgreSQLConnection(object):
    def __init__(self, dbname, user, password, host, port=5432):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
            )
            print("Conexion exitosa a la base de datos PostgreSQL")
            return True
        except Exception as e:
            print(f"Error de conexion: {e}")
            return False

    def execute_query(self, query, params=None, fetch_one=False):
        if not self.conn:
            print("No hay conexion a la base de datos. Intentando reconectar...")
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
            print(f"Error ejecutando la consulta: {str(e)}")
            print(f"Query: {query}")
            print(f"Parametros: {params}")
            raise e

    def close(self):
        if self.conn:
            self.conn.close()
            print("Conexion cerrada")
