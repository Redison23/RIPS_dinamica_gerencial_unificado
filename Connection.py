import psycopg2
import psycopg2.extras

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
                port=self.port
            )
            print("Conexión exitosa a la base de datos PostgreSQL")
            return True
        except Exception as e:
            print(f"Error de conexión: {e}")
            return False

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
            # Usamos RealDictCursor para mantener exactamente los nombres de columnas
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            
            # Verificar si es una consulta SELECT o similar que devuelve resultados
            if query.strip().upper().startswith("SELECT") or "RETURNING" in query.upper():
                if fetch_one:
                    result = cursor.fetchone()
                    cursor.close()
                    return result
                else:
                    results = cursor.fetchall()
                    cursor.close()
                    return results
            else:
                # Para UPDATE, INSERT, DELETE sin RETURNING
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
