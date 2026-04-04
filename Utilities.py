import os
import base64
import anyio.to_thread
from sql_server_conn import SQLServerConnection

class ToBase64:
    @staticmethod
    def xml_texto_a_base64(xml_texto):
        try:
            if isinstance(xml_texto, str):
                xml_texto = xml_texto.encode('utf-8')

            contenido_base64 = base64.b64encode(xml_texto).decode('utf-8')
            return contenido_base64
        except Exception as e:
            print(f"Error al convertir el texto XML a base64: {e}")
            return None

class Utilities:
    @staticmethod
    def get_db_connection():
        """Crea y abre una nueva conexión SQL Server para el request actual."""
        db = SQLServerConnection(
            server=os.getenv("DB_SERVER"),
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            driver=os.getenv("DB_DRIVER")
        )
        if not db.connect():
            raise ConnectionError("No se pudo establecer conexión con SQL Server")
        return db

    @staticmethod
    def configure_threadpool(logger=None):
        """
        Configura el tamaño del ThreadPool usado por FastAPI para endpoints sync (def).
        Controlado por la variable API_THREADPOOL_TOKENS (por defecto: 40).
        """
        tokens_raw = os.getenv("API_THREADPOOL_TOKENS", "40")
        try:
            tokens = int(tokens_raw)
            if tokens < 1:
                raise ValueError
        except ValueError:
            tokens = 40
            message = (
                f"Valor inválido en API_THREADPOOL_TOKENS='{tokens_raw}'. Usando {tokens}."
            )
            if logger:
                logger.warning(message)
            else:
                print(message)

        limiter = anyio.to_thread.current_default_thread_limiter()
        previous_tokens = limiter.total_tokens
        limiter.total_tokens = tokens

        message = (
            f"ThreadPool configurado: {previous_tokens} -> {tokens} hilos disponibles."
        )
        if logger:
            logger.info(message)
        else:
            print(message)

    @staticmethod
    def tiene_error_rvg18(result):
        """Verifica si el resultado contiene el error RVG18."""
        if not result or not result.get("errors"):
            return False

        for error in result["errors"]:
            if error.get("code") == "RVG18":
                return True

        return False

    @staticmethod
    def int_or_zero(value, default=0):
        """Convierte un valor a entero, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
        
    @staticmethod
    def int_or_one(value, default=1):
        """Convierte un valor a entero, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
        
    @staticmethod
    def format_datetime(value, format="%Y-%m-%d %H:%M"):
        """Formatea una fecha y hora al formato especificado YYYY-MM-DD HH:MM."""
        if not value:
            return ""
        
        # Importar datetime si no está ya importado
        from datetime import datetime
        
        try:
            # Si ya es un objeto datetime, formatearlo directamente
            if isinstance(value, datetime):
                return value.strftime(format)
            
            # Si es string, intentar parsearlo
            value_str = str(value).strip()
            
            # Intentar parsear diferentes formatos comunes
            date_formats = [
                "%Y-%m-%d %H:%M:%S.%f",  # 2024-01-01 12:30:45.123456
                "%Y-%m-%d %H:%M:%S",      # 2024-01-01 12:30:45
                "%Y-%m-%d %H:%M",         # 2024-01-01 12:30 (formato objetivo)
                "%Y-%m-%dT%H:%M:%S.%f",   # ISO format con microsegundos
                "%Y-%m-%dT%H:%M:%S",      # ISO format sin microsegundos
                "%Y-%m-%d",               # Solo fecha (agregará 00:00 como hora)
            ]
            
            for date_format in date_formats:
                try:
                    # Parsear sin cortar el string
                    parsed_date = datetime.strptime(value_str.split('.')[0] if '.' in value_str and 'T' in value_str else value_str, 
                                                    date_format.split('.')[0] if '.' in date_format else date_format)
                    return parsed_date.strftime(format)
                except (ValueError, IndexError):
                    continue
            
            # Si ningún formato funcionó, intentar extraer los primeros 16 caracteres
            if len(value_str) >= 16:
                # Verificar que tenga el formato correcto YYYY-MM-DD HH:MM
                if value_str[4] == '-' and value_str[7] == '-' and (value_str[10] == ' ' or value_str[10] == 'T') and value_str[13] == ':':
                    # Reemplazar T por espacio si existe
                    formatted = value_str[:16].replace('T', ' ')
                    return formatted
            
            # Si llegamos aquí, devolver vacío para evitar enviar formato inválido
            print(f"⚠️ Advertencia: No se pudo formatear la fecha '{value_str}', se retorna vacío")
            return ""
            
        except Exception as e:
            print(f"⚠️ Error formateando fecha '{value}': {e}")
            return ""
        
    @staticmethod
    def int_or_null(value, default=None):
        """Convierte un valor a entero, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
        
    @staticmethod
    def int_or_zero_one(value, default="01"):
        """Convierte un valor a entero, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None:
            return default
        try:
            return str(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def type_id(value, default="CC"):
        """Convierte un valor a cadena, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None:
            return default
        try:
            return str(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def number_id(value, default="99999999"):
        """Convierte un valor a cadena, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None:
            return default
        try:
            return str(value)
        except (ValueError, TypeError):
            return default
        
    @staticmethod
    def str_null(value, default="Null"):
        """Convierte un valor a cadena, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None or value == "":
            return default
        try:
            return str(value)
        except (ValueError, TypeError):
            return default
        
    @staticmethod
    def z000_diag(value, default="Z000"):
        """Convierte un valor a cadena, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None or value == "":
            return default
        try:
            return str(value)
        except (ValueError, TypeError):
            return default
        
    
    @staticmethod
    def valorPagoModerador(value, default=0):
        """Convierte un valor a cadena, devolviendo un valor predeterminado si es None o no se puede convertir."""
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
