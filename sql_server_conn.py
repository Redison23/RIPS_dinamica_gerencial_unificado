import pyodbc
import json
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
                # Conexión con autenticación de Windows
                connection_string = (
                    f"DRIVER={self.driver};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"Trusted_Connection=yes;"
                )
            else:
                # Conexión con usuario y contraseña
                connection_string = (
                    f"DRIVER={self.driver};"
                    f"SERVER={self.server};"
                    f"DATABASE={self.database};"
                    f"UID={self.username};"
                    f"PWD={self.password};"
                )
            
            self.conn = pyodbc.connect(connection_string)
            print("Conexión exitosa a la base de datos SQL Server")
            return True
        except Exception as e:
            print(f"Error de conexión: {e}")
            return False

    def _convert_row_to_dict(self, cursor, row):
        """Convierte una fila en un diccionario manteniendo los nombres exactos de las columnas"""
        if row is None:
            return None
        
        columns = [column[0] for column in cursor.description]
        row_dict = {}
        
        for i, value in enumerate(row):
            column_name = columns[i]
            # Convertir tipos especiales para serialización JSON si es necesario
            if isinstance(value, (Decimal,)):
                value = float(value)
            elif isinstance(value, (datetime, date)):
                value = value.isoformat() if value else None
            
            row_dict[column_name] = value
        
        return row_dict

    def execute_query(self, query, params=None, fetch_one=False):
        """
        Ejecuta una consulta SQL y devuelve los resultados como diccionarios si es SELECT,
        manteniendo los nombres exactos de las columnas de la base de datos.
        Para consultas UPDATE, INSERT, DELETE devuelve el número de filas afectadas.
        
        Args:
            query (str): Consulta SQL a ejecutar
            params (tuple): Parámetros para la consulta
            fetch_one (bool): Si True, devuelve solo un registro (fetchone)
        """
        if not self.conn:
            print("No hay conexión a la base de datos. Intentando reconectar...")
            self.connect()
            
        try:
            cursor = self.conn.cursor()
            
            # Ejecutar la consulta con o sin parámetros
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Verificar si es una consulta SELECT o similar que devuelve resultados
            if query.strip().upper().startswith("SELECT") or "OUTPUT" in query.upper():
                if fetch_one:
                    row = cursor.fetchone()
                    result = self._convert_row_to_dict(cursor, row)
                    cursor.close()
                    return result
                else:
                    rows = cursor.fetchall()
                    results = [self._convert_row_to_dict(cursor, row) for row in rows]
                    cursor.close()
                    return results
            else:
                # Para UPDATE, INSERT, DELETE sin OUTPUT
                self.conn.commit()
                rows_affected = cursor.rowcount
                cursor.close()
                return rows_affected  # Devuelve el número de filas afectadas
                
        except Exception as e:
            self.conn.rollback()
            print(f"Error ejecutando la consulta: {str(e)}")
            print(f"Query: {query}")
            print(f"Parámetros: {params}")
            raise e

    def close(self):
        if self.conn:
            self.conn.close()
            print("Conexión cerrada")