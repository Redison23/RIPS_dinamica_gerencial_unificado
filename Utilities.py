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
        """
        Verifica si el resultado contiene el error RVG18 (CUV ya aprobado previamente).
        Revisa tanto la estructura procesada (result['errors']) como la respuesta cruda
        del Ministerio (raw_response.data.ResultadosValidacion / errores), para no
        marcar como rechazada una factura que en realidad ya estaba reportada.
        """
        if not result:
            return False

        for error in (result.get("errors") or []):
            if isinstance(error, dict) and str(error.get("code", "")).upper() == "RVG18":
                return True

        raw_response = result.get("raw_response", result)
        if not isinstance(raw_response, dict):
            return False

        data = raw_response.get("data", raw_response)
        if not isinstance(data, dict):
            return False

        for validacion in (data.get("ResultadosValidacion") or []):
            if isinstance(validacion, dict) and str(validacion.get("Codigo", "")).upper() == "RVG18":
                return True

        for error in (data.get("errores") or []):
            if isinstance(error, dict):
                codigo = error.get("codigo", error.get("Codigo", ""))
                if str(codigo).upper() == "RVG18":
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

    @staticmethod
    def str_or_none(value):
        """
        Devuelve el valor como cadena, o None si es nulo/vacío. Evita enviar el literal
        'None' en campos opcionales (p. ej. codDiagnosticoPrincipalE) que el Ministerio
        rechaza por código de diagnóstico inválido.
        """
        if value is None:
            return None
        texto = str(value).strip()
        if texto == "" or texto.upper() in ("NULL", "NONE"):
            return None
        return texto

    # ------------------------------------------------------------------
    # Normalizaciones adaptadas de auraconnect-rips para reducir rechazos
    # ------------------------------------------------------------------

    @staticmethod
    def corregir_tipo_usuario(tipo_usuario):
        """
        Corrige el tipo de usuario. Solo se permiten 01, 02, 03, 04.
        Cualquier otro valor se reemplaza por 04.
        """
        permitidos = {'01', '02', '03', '04'}
        valor = str(tipo_usuario).strip().zfill(2)
        if valor not in permitidos:
            print(f"[CORRECCION] tipoUsuario {valor} -> 04")
            return '04'
        return valor

    @staticmethod
    def normalizar_tipo_documento_as(tipo_doc, edad):
        """Normaliza el tipo AS según la edad del usuario (RC<7, TI<18, CC en adelante)."""
        tipo_doc_upper = (tipo_doc or '').strip().upper()
        if tipo_doc_upper != 'AS':
            return tipo_doc_upper or tipo_doc

        if edad < 7:
            tipo_doc_corregido = 'RC'
        elif edad < 18:
            tipo_doc_corregido = 'TI'
        else:
            tipo_doc_corregido = 'CC'

        print(f"[CORRECCION] Tipo documento AS -> {tipo_doc_corregido} (edad: {edad})")
        return tipo_doc_corregido

    @staticmethod
    def corregir_tipo_documento(tipo_doc, fecha_nacimiento, fecha_referencia=None):
        """
        Corrige el tipo de documento según la edad del paciente (Colombia):
          - 0 a 6 años: RC ; 7 a 17 años: TI ; 18+ años: CC
        Solo corrige si el tipo actual es RC, TI, CC o AS. Otros (CE, PA, PE, MS...) no se tocan.
        La edad se calcula respecto a fecha_referencia (fecha de atención más temprana) o, si no,
        respecto a hoy.
        """
        from datetime import datetime, date

        tipos_colombianos = {'RC', 'TI', 'CC'}
        tipo_doc_upper = (tipo_doc or '').strip().upper()

        try:
            if isinstance(fecha_nacimiento, (datetime, date)):
                fecha_nac = fecha_nacimiento if isinstance(fecha_nacimiento, date) else fecha_nacimiento.date()
            else:
                fecha_str = str(fecha_nacimiento).strip()[:10]
                fecha_nac = datetime.strptime(fecha_str, '%Y-%m-%d').date()

            if fecha_referencia:
                if isinstance(fecha_referencia, (datetime, date)):
                    ref = fecha_referencia if isinstance(fecha_referencia, date) else fecha_referencia.date()
                else:
                    ref_str = str(fecha_referencia).strip()[:10]
                    ref = datetime.strptime(ref_str, '%Y-%m-%d').date()
            else:
                ref = date.today()

            edad = ref.year - fecha_nac.year - ((ref.month, ref.day) < (fecha_nac.month, fecha_nac.day))

            tipo_doc_corregido = Utilities.normalizar_tipo_documento_as(tipo_doc_upper, edad)
            if tipo_doc_corregido != tipo_doc_upper:
                return tipo_doc_corregido

            if tipo_doc_upper not in tipos_colombianos:
                return tipo_doc

            if edad < 7:
                tipo_correcto = 'RC'
            elif edad < 18:
                tipo_correcto = 'TI'
            else:
                tipo_correcto = 'CC'

            if tipo_doc_upper != tipo_correcto:
                print(f"[CORRECCION] Tipo documento {tipo_doc_upper} -> {tipo_correcto} (edad: {edad}, nacimiento: {fecha_nac}, ref: {ref})")
                return tipo_correcto

            return tipo_doc_upper

        except Exception as e:
            print(f"[WARNING] No se pudo corregir tipo documento: {e}")
            return tipo_doc

    @staticmethod
    def obtener_primera_fecha_atencion(servicios):
        """Fecha de atención más temprana de todos los servicios de un usuario (como date)."""
        from datetime import datetime
        primera = None
        for tipo, lista in servicios.items():
            for servicio in lista:
                fecha_str = (servicio.get('fechaInicioAtencion')
                             or servicio.get('fechaDispensAdmon')
                             or servicio.get('fechaSuministroTecnologia'))
                if not fecha_str:
                    continue
                try:
                    fecha = datetime.strptime(str(fecha_str).strip()[:16], '%Y-%m-%d %H:%M').date()
                except Exception:
                    try:
                        fecha = datetime.strptime(str(fecha_str).strip()[:10], '%Y-%m-%d').date()
                    except Exception:
                        continue
                if primera is None or fecha < primera:
                    primera = fecha
        return primera

    @staticmethod
    def obtener_periodo_facturacion_xml(xml_data):
        """
        Extrae el periodo de facturación (InvoicePeriod) de un XML de factura electrónica.
        Recibe el XML ya cargado (string). Retorna (fecha_inicio, fecha_fin) como date, o (None, None).
        """
        from datetime import datetime
        import re

        try:
            if not xml_data:
                return None, None
            period_match = re.search(
                r'<cac:InvoicePeriod>\s*<cbc:StartDate>([\d-]+)</cbc:StartDate>\s*<cbc:EndDate>([\d-]+)</cbc:EndDate>\s*</cac:InvoicePeriod>',
                xml_data
            )
            if period_match:
                inicio = datetime.strptime(period_match.group(1), '%Y-%m-%d').date()
                fin = datetime.strptime(period_match.group(2), '%Y-%m-%d').date()
                print(f"[PERIODO XML] Periodo de facturación del XML: {inicio} a {fin}")
                return inicio, fin
        except Exception as e:
            print(f"[WARNING] Error obteniendo periodo del XML: {e}")

        return None, None

    @staticmethod
    def ajustar_fechas_al_periodo(servicios, fecha_factura, periodo_inicio=None, periodo_fin=None):
        """
        Mueve al periodo de facturación las fechas de servicio que caen fuera de rango
        (antes del inicio o en el futuro), evitando el rechazo RVC014. Si se pasan
        periodo_inicio/periodo_fin (del XML), se usan; si no, se derivan del mes de
        fecha_factura. Solo toca fechas fuera de rango. Devuelve cuántas se ajustaron.
        """
        from datetime import datetime, date, timedelta, time
        import calendar
        import random

        if periodo_inicio and periodo_fin:
            primer_dia = periodo_inicio
            ultimo_dia = periodo_fin
        else:
            if not fecha_factura:
                return 0
            if isinstance(fecha_factura, str):
                fecha_factura = datetime.strptime(fecha_factura[:10], '%Y-%m-%d').date()
            elif isinstance(fecha_factura, datetime):
                fecha_factura = fecha_factura.date()
            anio = fecha_factura.year
            mes = fecha_factura.month
            primer_dia = date(anio, mes, 1)
            ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])

        print(f"[AJUSTE PERIODO] Usando periodo: {primer_dia} a {ultimo_dia}")

        ahora = datetime.now().replace(second=0, microsecond=0)
        fecha_maxima_permitida = datetime.combine(ultimo_dia, time(23, 59))
        if primer_dia <= ahora.date() <= ultimo_dia:
            fecha_maxima_permitida = min(fecha_maxima_permitida, ahora)

        campos_fecha = {
            'consultas': ['fechaInicioAtencion'],
            'procedimientos': ['fechaInicioAtencion'],
            'urgencias': ['fechaInicioAtencion', 'fechaEgreso'],
            'hospitalizacion': ['fechaInicioAtencion', 'fechaEgreso'],
            'recienNacidos': ['fechaNacimiento', 'fechaEgreso'],
            'medicamentos': ['fechaDispensAdmon'],
            'otrosServicios': ['fechaSuministroTecnologia'],
        }

        total_ajustados = 0
        for tipo, lista in servicios.items():
            campos = campos_fecha.get(tipo, [])
            if not campos:
                continue
            for item in lista:
                for campo in campos:
                    fecha_str = item.get(campo)
                    if not fecha_str:
                        continue
                    try:
                        fecha_dt = datetime.strptime(str(fecha_str).strip()[:16], '%Y-%m-%d %H:%M')
                        fecha_solo = fecha_dt.date()
                        if fecha_solo < primer_dia:
                            limite_inicio = min(primer_dia + timedelta(days=6), fecha_maxima_permitida.date())
                            if limite_inicio < primer_dia:
                                continue
                            nuevo_dia = primer_dia + timedelta(days=random.randint(0, (limite_inicio - primer_dia).days))
                            nueva_fecha = fecha_dt.replace(year=nuevo_dia.year, month=nuevo_dia.month, day=nuevo_dia.day)
                            if nueva_fecha > fecha_maxima_permitida:
                                nueva_fecha = fecha_maxima_permitida
                            item[campo] = nueva_fecha.strftime('%Y-%m-%d %H:%M')
                            total_ajustados += 1
                            print(f"[AJUSTE PERIODO] {tipo}.{campo}: {fecha_str} -> {item[campo]}")
                        elif fecha_dt > fecha_maxima_permitida:
                            primer_dia_final = max(primer_dia, fecha_maxima_permitida.date() - timedelta(days=6))
                            nuevo_dia = fecha_maxima_permitida.date() - timedelta(days=random.randint(0, (fecha_maxima_permitida.date() - primer_dia_final).days))
                            nueva_fecha = fecha_dt.replace(year=nuevo_dia.year, month=nuevo_dia.month, day=nuevo_dia.day)
                            if nueva_fecha > fecha_maxima_permitida:
                                nueva_fecha = fecha_maxima_permitida
                            item[campo] = nueva_fecha.strftime('%Y-%m-%d %H:%M')
                            total_ajustados += 1
                            print(f"[AJUSTE PERIODO] {tipo}.{campo}: {fecha_str} -> {item[campo]}")
                    except Exception:
                        pass

        # Corregir fechaEgreso < fechaInicioAtencion (RVC039)
        total_ajustados += Utilities.corregir_fechas_ingreso_egreso(servicios)
        return total_ajustados

    @staticmethod
    def corregir_fechas_ingreso_egreso(servicios):
        """
        Corrige servicios donde la fecha de egreso es anterior o igual a la de ingreso
        (error RVC039). El egreso debe quedar POSTERIOR al ingreso pero SIN salir del día de
        atención ni quedar en el futuro respecto a la validación de los RIPS (RVC043/RVC044).

        Antes se sumaban horas ALEATORIAS (2-48h), lo que en facturas EVENTO (urgencias del
        mismo día, ingreso==egreso) empujaba el egreso al día siguiente o al futuro y provocaba
        rechazos RVC043/RVC044 sin devolver CUV. Ahora se usa un incremento mínimo y acotado
        (1 hora; 1 minuto si esa hora cae en el futuro) y, si ni siquiera +1 minuto es válido
        (ingreso demasiado reciente o en el futuro), se deja el dato original para no arriesgar
        un RVC043 (es un problema del dato de origen, no de este ajuste).

        Aplica a hospitalización, urgencias y recién nacidos. Devuelve cuántos corrigió.
        Esta función solo se ejecuta en la ruta EVENTO (en CAPITA se ajusta por periodo).
        """
        from datetime import datetime, timedelta

        tipos_con_egreso = {
            'hospitalizacion': ('fechaInicioAtencion', 'fechaEgreso'),
            'urgencias': ('fechaInicioAtencion', 'fechaEgreso'),
            'recienNacidos': ('fechaNacimiento', 'fechaEgreso'),
        }

        total_corregidos = 0
        for tipo, (campo_ingreso, campo_egreso) in tipos_con_egreso.items():
            for item in servicios.get(tipo, []):
                ingreso_str = item.get(campo_ingreso)
                egreso_str = item.get(campo_egreso)
                if not ingreso_str or not egreso_str:
                    continue
                try:
                    ingreso_dt = datetime.strptime(str(ingreso_str).strip()[:16], '%Y-%m-%d %H:%M')
                    egreso_dt = datetime.strptime(str(egreso_str).strip()[:16], '%Y-%m-%d %H:%M')
                    if ingreso_dt >= egreso_dt:
                        ahora = datetime.now()
                        nuevo_egreso = ingreso_dt + timedelta(hours=1)
                        if nuevo_egreso > ahora:
                            nuevo_egreso = ingreso_dt + timedelta(minutes=1)
                        if nuevo_egreso > ahora:
                            # Ingreso demasiado reciente o en el futuro: no se puede garantizar
                            # egreso>ingreso sin quedar en el futuro (RVC043). Se respeta el dato.
                            continue
                        item[campo_egreso] = nuevo_egreso.strftime('%Y-%m-%d %H:%M')
                        total_corregidos += 1
                        print(f"[AJUSTE EGRESO] {tipo}: ingreso={ingreso_str}, egreso={egreso_str} -> {item[campo_egreso]}")
                except Exception:
                    pass

        return total_corregidos
