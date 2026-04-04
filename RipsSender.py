import requests
import json
import time
from datetime import datetime, timedelta
import os
import glob

class RipsSender:
    """
    Clase encargada de enviar las facturas en formato JSON al ministerio mediante
    solicitudes HTTP.
    """
    PAQUETES_ENDPOINTS = {
        # Facturación evento / normal
        "FEV_RIPS": "/api/PaquetesFevRips/CargarFevRips",
        "NC": "/api/PaquetesFevRips/CargarNC",
        "NC_TOTAL": "/api/PaquetesFevRips/CargarNCTotal",
        "ND": "/api/PaquetesFevRips/CargarND",
        "NOTA_AJUSTE": "/api/PaquetesFevRips/CargarNotaAjuste",
        "NC_ACUERDO_VOLUNTADES": "/api/PaquetesFevRips/CargarNCAcuerdoVoluntades",
        # Capita
        "CAPITA_INICIAL": "/api/PaquetesFevRips/CargarCapitaInicial",
        "CAPITA_PERIODO": "/api/PaquetesFevRips/CargarCapitaPeriodo",
        "CAPITA_FINAL": "/api/PaquetesFevRips/CargarCapitaFinal",
        # Consultas
        "CONSULTAR_CUV": "/api/ConsultasFevRips/ConsultarCUV"
    }
    LOG_RETENTION_DAYS = 30

    def __init__(self, base_url, token=None, timeout=30, max_retries=3, verify_ssl=False):
        """
        Inicializa el cliente para envío de facturas.
        
        Args:
            base_url (str): URL base del API del ministerio
            token (str, optional): Token de autenticación
            timeout (int, optional): Tiempo máximo de espera para la respuesta en segundos
            max_retries (int, optional): Número máximo de reintentos en caso de error
            verify_ssl (bool, optional): Si se debe verificar el certificado SSL
        """
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.verify = verify_ssl  # Para manejar certificados SSL autofirmados
    
    def set_token(self, token):
        """Actualiza el token de autenticación"""
        self.token = token

    def get_endpoint_catalog(self):
        """Retorna el catálogo de operaciones soportadas."""
        return dict(self.PAQUETES_ENDPOINTS)
    
    def _get_headers(self):
        """Devuelve los headers necesarios para las solicitudes"""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
            
        return headers
    
    def _handle_response(self, response):
        """
        Maneja la respuesta de la API y devuelve un diccionario con el resultado.
        Procesa TODOS los códigos HTTP (200, 400, 422, 500, etc.) para extraer datos de validación.
        
        Args:response (requests.Response): Respuesta de la API
        Returns: dict: Diccionario con los resultados
        """
        result = {
            'success': False, 
            'status_code': response.status_code, 
            'data': None, 
            'message': '', 
            'error': None,
            'has_validation_data': False  # Nuevo flag para indicar si hay datos de validación
        }
        
        try:
            # Intentar obtener el cuerpo JSON de la respuesta
            data = response.json()
            result['data'] = data
            
            # Verificar si hay datos de validación (ResultadosValidacion) independientemente del código HTTP
            if isinstance(data, dict) and 'ResultadosValidacion' in data:
                result['has_validation_data'] = True
                print(f"[RESPONSE] Código HTTP {response.status_code} con datos de validación")
            
            # Verificar si fue exitoso basado en el código de estado
            if 200 <= response.status_code < 300:
                result['success'] = True
                result['message'] = 'Operación exitosa'
            else:
                # Registrar el código HTTP pero aún así procesar los datos
                result['message'] = f"HTTP {response.status_code}"
                if isinstance(data, dict):
                    result['error'] = data.get('message', data.get('error', f'HTTP {response.status_code}'))
                else:
                    result['error'] = f'HTTP {response.status_code}'
                print(f"[RESPONSE] HTTP {response.status_code}, procesando datos de respuesta...")
                
        except ValueError:
            # La respuesta no es JSON válido
            result['message'] = 'La respuesta no contiene JSON válido'
            result['error'] = response.text
            print(f"[RESPONSE] HTTP {response.status_code}, respuesta no es JSON")
            
        except Exception as e:
            # Otro tipo de error al procesar la respuesta
            result['message'] = 'Error al procesar la respuesta'
            result['error'] = str(e)
            print(f"[RESPONSE] Error procesando respuesta: {str(e)}")
            
        return result
    
    def authenticate(self, tipo_documento, numero_documento, clave, nit):
        """
        Autentica con el servicio SISPRO y obtiene un token.
        
        Args:
            tipo_documento (str): Tipo de documento (CC, CE, etc.)
            numero_documento (str): Número de documento
            clave (str): Contraseña
            nit (str): NIT de la institución
            
        Returns:
            dict: Resultado de la autenticación incluyendo el token si fue exitoso
        """
        auth_url = f"{self.base_url}/api/Auth/LoginSISPRO"
        auth_data = {
            "persona": {
                "identificacion": {
                    "tipo": tipo_documento,
                    "numero": numero_documento
                }
            },
            "clave": clave,
            "nit": nit
        }
        
        try:
            response = self.session.post(
                auth_url,
                json=auth_data,
                timeout=self.timeout,
                verify=self.session.verify
            )
            
            result = self._handle_response(response)
            
            # Modificamos para manejar la estructura real de la respuesta
            if result['success'] and result['data']:
                if 'token' in result['data'] and result['data']['login'] is True:
                    self.token = result['data']['token']
                    result['message'] = 'Autenticación exitosa'
                elif result['data'].get('errors'):
                    result['success'] = False
                    result['error'] = result['data']['errors']
                    result['message'] = f"Error de autenticación: {result['data']['errors']}"
                elif not result['data'].get('login'):
                    result['success'] = False
                    result['error'] = "Login fallido"
                    result['message'] = "Error de autenticación: credenciales inválidas"
        
            return result
            
        except requests.RequestException as e:
            return {
                'success': False,
                'status_code': None,
                'data': None,
                'message': 'Error de conexión durante la autenticación',
                'error': str(e)
            }
    
    def send_paquete(self, payload_json, tipo_paquete='CAPITA_FINAL', log_response=True, invoice_number=None):
        """
        Envía un paquete al ministerio según el tipo de operación.

        Args:
            payload_json (dict): Cuerpo JSON a enviar
            tipo_paquete (str): Clave de operación (FEV_RIPS, NC, ND, CAPITA_FINAL, etc.)
            log_response (bool): Si es True, registra la respuesta
            invoice_number (str, optional): Número de factura para log (fallback)

        Returns:
            dict: Resultado procesado + respuesta cruda
        """
        if not self.token:
            return {
                'success': False,
                'message': 'No hay token de autenticación configurado',
                'error': 'Se requiere autenticación previa',
                'status_code': None,
                'data': None
            }

        tipo_paquete_upper = tipo_paquete.upper()
        if tipo_paquete_upper not in self.PAQUETES_ENDPOINTS:
            return {
                'success': False,
                'message': f'Tipo de paquete inválido: {tipo_paquete}',
                'error': f'Debe ser uno de: {", ".join(sorted(self.PAQUETES_ENDPOINTS.keys()))}',
                'status_code': None,
                'data': None
            }

        endpoint_path = self.PAQUETES_ENDPOINTS[tipo_paquete_upper]
        endpoint_url = f"{self.base_url}{endpoint_path}"
        print(f"[ENVIO] Operación: {tipo_paquete_upper} - Endpoint: {endpoint_url}")

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.post(
                    endpoint_url,
                    json=payload_json,
                    headers=self._get_headers(),
                    timeout=self.timeout,
                    verify=self.session.verify
                )

                result = self._handle_response(response)

                if result['success'] or response.status_code not in [408, 429, 500, 502, 503, 504]:
                    break

                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    print(f"Reintentando en {wait_time} segundos... (intento {attempt}/{self.max_retries})")
                    time.sleep(wait_time)

            except requests.RequestException as e:
                result = {
                    'success': False,
                    'status_code': None,
                    'data': None,
                    'message': f'Error de conexión en el intento {attempt}/{self.max_retries}',
                    'error': str(e)
                }

                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    print(f"Reintentando en {wait_time} segundos... (intento {attempt}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    break

        if log_response:
            numero_para_log = (
                invoice_number
                or payload_json.get("rips", {}).get("numFactura")
                or payload_json.get("numFactura")
                or tipo_paquete_upper.lower()
            )
            self._log_response(numero_para_log, result)

        processed_result = self.process_invoice_response(result)
        processed_result['raw_response'] = result
        processed_result['operation'] = tipo_paquete_upper
        processed_result['endpoint'] = endpoint_path
        return processed_result

    def send_invoice(self, invoice_json, tipo_cargue='FINAL', log_response=True):
        """
        Envía una factura al ministerio.
        
        Args:
            invoice_json (dict): Factura en formato JSON
            tipo_cargue (str): Tipo de cargue a realizar. Opciones: 'INICIAL', 'FINAL'
                - INICIAL: Para el primer cargue de capita (solo XML)
                - FINAL: Para el cargue final de capita con RIPS completos (default)
            log_response (bool, optional): Si es True, registra la respuesta en un archivo de log
            
        Returns:
            dict: Resultado del envío con información procesada
        """
        # Compatibilidad: mantener API existente para CAPITA.
        tipo_cargue_upper = tipo_cargue.upper()
        compat_map = {
            'INICIAL': 'CAPITA_INICIAL',
            'FINAL': 'CAPITA_FINAL'
        }

        if tipo_cargue_upper not in compat_map:
            return {
                'success': False,
                'message': f'Tipo de cargue inválido: {tipo_cargue}',
                'error': f'Debe ser INICIAL o FINAL',
                'status_code': None,
                'data': None
            }

        return self.send_paquete(
            invoice_json,
            tipo_paquete=compat_map[tipo_cargue_upper],
            log_response=log_response
        )

    def _cleanup_old_envio_logs(self, log_dir="logs"):
        """
        Elimina archivos envios_YYYYMMDD.log con antiguedad mayor a LOG_RETENTION_DAYS.
        """
        try:
            cutoff_date = (datetime.now() - timedelta(days=self.LOG_RETENTION_DAYS)).date()
            pattern = os.path.join(log_dir, "envios_*.log")
            for file_path in glob.glob(pattern):
                file_name = os.path.basename(file_path)
                if not (file_name.startswith("envios_") and file_name.endswith(".log")):
                    continue

                date_part = file_name[len("envios_"):-len(".log")]
                if len(date_part) != 8 or not date_part.isdigit():
                    continue

                file_date = datetime.strptime(date_part, "%Y%m%d").date()
                if file_date < cutoff_date:
                    os.remove(file_path)
        except Exception as e:
            print(f"[ATENCION] No se pudo limpiar logs antiguos de envios: {str(e)}")
    
    def _log_response(self, invoice_number, result):
        """
        Registra la respuesta en un archivo de log.
        
        Args:
            invoice_number (str): Número de la factura
            result (dict): Resultado del envío
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Procesar la respuesta para el log
        processed_result = self.process_invoice_response(result)
        
        log_entry = {
            "timestamp": timestamp,
            "invoice": invoice_number,
            "success": processed_result['success'],
            "state": processed_result['state'],
            "validation_code": processed_result['validation_code'],
            "date": processed_result['date'],
            "errors": len(processed_result['errors']),
            "warnings": len(processed_result['warnings']),
            "notifications": len(processed_result['notifications']),
            "details": {
                "errors": processed_result['errors'],
                "warnings": processed_result['warnings'],
                "notifications": processed_result['notifications']
            }
        }
        
        log_file = f"logs/envios_{datetime.now().strftime('%Y%m%d')}.log"
        
        # Asegurarse de que el directorio de logs existe
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        self._cleanup_old_envio_logs(os.path.dirname(log_file))
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
    
    def process_invoice_response(self, result):
        """
        Procesa la respuesta específica del envío de facturas RIPS.
        
        Args:
            result (dict): Resultado obtenido del envío de la factura
            
        Returns:
            dict: Información procesada con estado, mensajes y detalles
        """
        processed = {
            'success': False,
            'state': None,
            'invoice_number': None,
            'validation_code': None,
            'date': None,
            'errors': [],
            'warnings': [],
            'notifications': []
        }
        
        # Log de debugging
        print(f"[PROCESS_RESPONSE] result keys: {list(result.keys())}")
        print(f"[PROCESS_RESPONSE] status_code: {result.get('status_code')}")
        print(f"[PROCESS_RESPONSE] success: {result.get('success')}")
        print(f"[PROCESS_RESPONSE] has_validation_data: {result.get('has_validation_data')}")
        
        # Verificar si hay datos para procesar
        if not result.get('data'):
            processed['errors'].append({
                'message': result.get('message', 'Error en el envío'),
                'details': result.get('error', 'No hay detalles disponibles')
            })
            print(f"[PROCESS_RESPONSE] No hay datos, retornando con error")
            return processed
        
        # Procesar respuesta específica de SISPRO (incluso si result['success'] es False)
        data = result['data']
        print(f"[PROCESS_RESPONSE] data keys: {list(data.keys()) if isinstance(data, dict) else 'NO ES DICT'}")
        processed['success'] = data.get('ResultState', False)
        processed['state'] = 'APROBADO' if data.get('ResultState', False) else 'RECHAZADO'
        processed['invoice_number'] = data.get('NumFactura')
        processed['validation_code'] = data.get('CodigoUnicoValidacion')
        processed['date'] = data.get('FechaRadicacion')
        
        # Procesar resultados de validación
        for validation in data.get('ResultadosValidacion', []):
            validation_item = {
                'code': validation.get('Codigo'),
                'description': validation.get('Descripcion'),
                'observations': validation.get('Observaciones'),
                'path': validation.get('PathFuente'),
                'source': validation.get('Fuente')
            }
            
            # Clasificar por tipo de validación
            validation_class = validation.get('Clase', '').upper()
            if validation_class == 'RECHAZADO':
                processed['errors'].append(validation_item)
            elif validation_class == 'NOTIFICACION':
                processed['notifications'].append(validation_item)
        
        # Actualizar el estado final basado en los errores
        if processed['errors']:
            processed['success'] = False
        
        return processed
    
    def _extract_cuv_from_rvg18_error(self, result):
        """
        Extrae el código CUV de un error RVG18 en la respuesta.
        
        Args:
            result (dict): Resultado procesado del envío
            
        Returns:
            str: Código CUV extraído o cadena vacía si no se encuentra
        """
        try:
            # Buscar en errores (estructura procesada)
            if 'errors' in result and result['errors']:
                for error in result['errors']:
                    if error.get('code') == 'RVG18':
                        cuv_observaciones = error.get('observations', '')
                        if cuv_observaciones and len(cuv_observaciones) > 50:  # Validar que sea un CUV real
                            return cuv_observaciones
            
            # Buscar en raw_response si existe
            if result.get('raw_response') and result['raw_response'].get('data'):
                raw_data = result['raw_response']['data']
                resultados_validacion = raw_data.get('ResultadosValidacion', [])
                for validacion in resultados_validacion:
                    if (validacion.get('Clase') == 'RECHAZADO' and 
                        validacion.get('Codigo') == 'RVG18'):
                        cuv_observaciones = validacion.get('Observaciones', '')
                        if cuv_observaciones and len(cuv_observaciones) > 50:  # Validar que sea un CUV real
                            return cuv_observaciones
            
            return ""
            
        except Exception as e:
            print(f"[ATENCION] Error extrayendo CUV de RVG18: {str(e)}")
            return ""
    
    #Actualizacion en base de datos
    def update_invoice_status(self, conn, num_factura, result, tipo_cargue='FINAL'):
        """
        Actualiza el estado de la factura en la base de datos con el resultado del envío
        y guarda las notificaciones y rechazos en la tabla rips_notifica.
        
        Args:
            conn: Conexión a la base de datos
            num_factura (str): Número de factura
            result (dict): Resultado procesado del envío
            tipo_cargue (str): Tipo de cargue realizado ('INICIAL' o 'FINAL')
            
        Returns:
            bool: True si la actualización fue exitosa, False en caso contrario
        """
        print(f"[UPDATE_INVOICE_STATUS] INICIO - Factura: {num_factura}, Tipo: {tipo_cargue}")
        print(f"[UPDATE_INVOICE_STATUS] Errores en result: {len(result.get('errors', []))}")
        
        try:
            # Determinar el código de retorno (estado de la factura) - varchar(15)
            codigo_retorno = "APROBADO" if result['success'] else "RECHAZADO"
            if codigo_retorno and len(codigo_retorno) > 15:
                codigo_retorno = codigo_retorno[:15]  # Truncar si excede la longitud
            
            # Obtener el código CUV (en caso de aprobación) - varchar(200)
            codigo_cuv = ""  # Inicializamos con cadena vacía por defecto

            # Solo asignamos un valor si el envío fue exitoso y hay un código válido
            if result['success'] and result['validation_code']:
                if " " not in result['validation_code']:
                    codigo_cuv = result['validation_code']
            
            # Si no hay CUV y hay errores, intentar extraer el CUV del error RVG18
            if not codigo_cuv:
                cuv_from_rvg18 = self._extract_cuv_from_rvg18_error(result)
                if cuv_from_rvg18:
                    codigo_cuv = cuv_from_rvg18
                    print(f"[INFO] CUV extraído de RVG18 para factura {num_factura}: {codigo_cuv[:20]}...")
            
            # Truncar si excede la longitud
            if codigo_cuv and len(codigo_cuv) > 200:
                codigo_cuv = codigo_cuv[:200]  # Truncar si excede la longitud
            
            # Obtener la fecha de radicación/retorno - usar objeto datetime directamente
            if result['date']:
                try:
                    from datetime import datetime
                    fecha_str = result['date']
                    # Remover la Z del final si existe
                    if fecha_str.endswith('Z'):
                        fecha_str = fecha_str[:-1]
                    # Remover información de zona horaria (+00:00 o similar)
                    if '+' in fecha_str:
                        fecha_str = fecha_str.split('+')[0]
                    # Remover microsegundos si existen (todo después del punto decimal en segundos)
                    if '.' in fecha_str:
                        fecha_str = fecha_str.split('.')[0]
                    # Convertir a datetime object (NO a string)
                    fecha_retorno = datetime.fromisoformat(fecha_str.replace('T', ' '))
                except Exception as e:
                    print(f"[ATENCION] Error formateando la fecha: {str(e)}. Usando fecha actual.")
                    from datetime import datetime
                    fecha_retorno = datetime.now()
            else:
                from datetime import datetime
                fecha_retorno = datetime.now()
            
            print(f"  - Código CUV: {codigo_cuv}")
            print(f"  - Código Retorno: {codigo_retorno}")
            
            # 1. Actualizar estado en la tabla rips_af según el tipo de cargue
            if tipo_cargue.upper() == 'INICIAL':
                # Para cargue INICIAL: solo actualizar codigo_cuv
                query_update_af = """
                    UPDATE dbo.rips_af SET codigo_cuv = ? WHERE [numFactura] = ?
                """
                rows_affected = conn.execute_query(query_update_af, (codigo_cuv, num_factura))
                print(f"[INFO] Cargue INICIAL - Solo actualizado codigo_cuv")
            else:  # FINAL
                # Para cargue FINAL: actualizar codigo_cuv_global, codigo_retorno y fecha_retorno
                query_update_af = """
                    UPDATE dbo.rips_af SET codigo_cuv_global = ?, codigo_retorno = ?, fecha_retorno = ? WHERE [numFactura] = ?
                """
                rows_affected = conn.execute_query(query_update_af, (codigo_cuv, codigo_retorno, fecha_retorno, num_factura))
                print(f"[INFO] Cargue FINAL - Actualizado codigo_cuv_global, codigo_retorno y fecha_retorno")
            
            # 2. Guardar notificaciones y rechazos en la tabla rips_notifica
            # Determinar el tipo de factura basado en el tipo_cargue
            tipo_factura_notifica = 'INICIAL' if tipo_cargue.upper() == 'INICIAL' else 'FINAL'
            
            # Eliminar notificaciones anteriores solo del mismo tipo de factura
            query_delete_notifica = """
                DELETE FROM dbo.rips_notifica 
                WHERE numfactura = ? AND tipo_factura = ?
            """
            notificaciones_eliminadas = conn.execute_query(query_delete_notifica, (num_factura, tipo_factura_notifica))
            
            if notificaciones_eliminadas > 0:
                print(f"[LIMPIEZA] Eliminadas {notificaciones_eliminadas} notificación(es) anterior(es) de factura {num_factura} tipo {tipo_factura_notifica}")

            total_validaciones = 0
            
            # Log detallado para debugging
            log_file = f"logs/envios_{datetime.now().strftime('%Y%m%d')}.log"
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            self._cleanup_old_envio_logs(os.path.dirname(log_file))
            
            debug_info = {
                "timestamp": datetime.now().isoformat(),
                "action": "UPDATE_STATUS_DEBUG",
                "factura": num_factura,
                "tipo_cargue": tipo_cargue,
                "tipo_factura_notifica": tipo_factura_notifica,
                "result_keys": list(result.keys()),
                "has_errors": 'errors' in result,
                "errors_count": len(result.get('errors', [])),
                "errors_data": result.get('errors', [])
            }
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(debug_info, ensure_ascii=False, default=str) + "\n")
            
            print(f"[UPDATE_STATUS] Factura: {num_factura}, Tipo: {tipo_cargue}")
            print(f"[UPDATE_STATUS] result keys: {list(result.keys())}")
            print(f"[UPDATE_STATUS] result['errors']: {result.get('errors', 'NO_EXISTE')}")
            
            if 'errors' in result and result['errors']:
                total_validaciones += len(result['errors'])
                print(f"[UPDATE_STATUS] Guardando {len(result['errors'])} error(es) en rips_notifica tipo {tipo_factura_notifica}")
                for error in result['errors']:
                    print(f"[INFO] Insertando error: [{error.get('code', '')}] {error.get('description', '')[:50]}...")
                    query_insert_notif = """
                        INSERT INTO dbo.rips_notifica 
                        (numfactura, notclase, notcodigo, notdescri, notobserv, notpathfu, notfuente, tipo_factura)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    try:
                        rows_inserted = conn.execute_query(
                            query_insert_notif, 
                            (
                                num_factura,
                                'RECHAZADO',
                                error.get('code', ''),
                                error.get('description', ''),
                                error.get('observations', ''),
                                error.get('path', ''),
                                error.get('source', ''),
                                tipo_factura_notifica
                            )
                        )
                        print(f"[OK] Error insertado correctamente (rows: {rows_inserted})")
                    except Exception as e:
                        print(f"[ERROR] Error al insertar en rips_notifica: {str(e)}")
                        
            if 'notifications' in result and result['notifications']:
                total_validaciones += len(result['notifications'])
                for notification in result['notifications']:
                    query_insert_notif = """
                        INSERT INTO dbo.rips_notifica 
                        (numfactura, notclase, notcodigo, notdescri, notobserv, notpathfu, notfuente, tipo_factura)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    conn.execute_query(
                        query_insert_notif, 
                        (
                            num_factura,
                            'NOTIFICACION',
                            notification.get('code', ''),
                            notification.get('description', ''),
                            notification.get('observations', ''),
                            notification.get('path', ''),
                            notification.get('source', ''),
                            tipo_factura_notifica
                        )
                    )
            
            if rows_affected > 0:
                return True
            else:
                print(f"[ATENCION] No se actualizó ninguna fila para la factura {num_factura}")
                if total_validaciones > 0:
                    print(f"[OK] {total_validaciones} validación(es) guardada(s) en rips_notifica")
                return False
                
        except Exception as e:
            print(f"[ERROR] Error actualizando la factura {num_factura} en la base de datos: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False
        
    def save_json_soporte_to_db(self, conn, result, invoice_number=None, tipo_factura='FINAL'):
        """
        Guarda la información del JSON soporte en las tablas datos_json_soporte 
        y json_soporte_resultado_validacion.
        
        Args:
            conn: Conexión a la base de datos
            result (dict): Resultado procesado del envío que contiene raw_response
            invoice_number (str): Número de factura explícito (opcional, se usa como fallback)
            tipo_factura (str): Tipo de factura ('INICIAL' o 'FINAL')
            
        Returns:
            bool: True si la operación fue exitosa, False en caso contrario
        """
        try:
            # Verificar que tenemos los datos necesarios
            if not result.get('raw_response') or not result['raw_response'].get('data'):
                print("[ATENCION] No hay datos raw_response para guardar en JSON soporte")
                return False
            
            raw_data = result['raw_response']['data']
            
            # Extraer datos principales con validaciones mejoradas
            result_state = raw_data.get('ResultState', False)
            proceso_id = raw_data.get('ProcesoId', 0)
            
            # Para el número de factura, usar en orden de prioridad:
            # 1. El parámetro explícito invoice_number
            # 2. El del result procesado
            # 3. El del raw_data
            num_factura = invoice_number or result.get('invoice_number') or raw_data.get('NumFactura', '')
            
            print(f"[DEBUG] Número de factura para JSON soporte:")
            print(f"   - Parámetro explícito: {invoice_number}")
            print(f"   - result.invoice_number: {result.get('invoice_number')}")
            print(f"   - raw_data.NumFactura: {raw_data.get('NumFactura')}")
            print(f"   - Valor final: {num_factura}")
            
            if not num_factura or num_factura == '0':
                print("[ATENCION] Número de factura no válido, saltando guardado de JSON soporte")
                return False
            
            # Lógica para obtener el código único de validación
            codigo_unico_validacion = raw_data.get('CodigoUnicoValidacion', '')
            
            # Si es rechazada, buscar el error RVG18 para extraer el CUV real
            if not result_state:  # Si es rechazada (ResultState = False)
                resultados_validacion = raw_data.get('ResultadosValidacion', [])
                for validacion in resultados_validacion:
                    if (validacion.get('Clase') == 'RECHAZADO' and 
                        validacion.get('Codigo') == 'RVG18'):
                        # Extraer el CUV de las observaciones
                        cuv_observaciones = validacion.get('Observaciones', '')
                        if cuv_observaciones and len(cuv_observaciones) > 50:  # Validar que sea un CUV real
                            codigo_unico_validacion = cuv_observaciones
                            print(f"[INFO] CUV extraído de RVG18 para factura {num_factura}: {cuv_observaciones[:20]}...")
                        break

            fecha_radicacion = raw_data.get('FechaRadicacion', '')
            ruta_archivos = raw_data.get('RutaArchivos')  # Puede ser null
            
            # Ajustar fecha para SQL Server
            if fecha_radicacion:
                try:
                    from datetime import datetime
                    fecha_str = fecha_radicacion
                    # Si termina en Z (UTC), quitarla
                    if fecha_str.endswith('Z'):
                        fecha_str = fecha_str[:-1]
                    # Remover información de zona horaria (+00:00 o similar)
                    if '+' in fecha_str:
                        fecha_str = fecha_str.split('+')[0]
                    # Remover microsegundos si existen
                    if '.' in fecha_str:
                        fecha_str = fecha_str.split('.')[0]
                    # Convertir a datetime y luego a formato SQL Server compatible
                    fecha_dt = datetime.fromisoformat(fecha_str.replace('T', ' '))
                    fecha_radicacion = fecha_dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception as e:
                    print(f"[ATENCION] Error formateando fecha para JSON soporte: {str(e)}")
                    from datetime import datetime
                    fecha_radicacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                from datetime import datetime
                fecha_radicacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Eliminar registros existentes de esta factura y tipo antes de insertar nuevos
            self._delete_existing_json_soporte_records(conn, num_factura, tipo_factura)
            
            # 1. Insertar en rips_datos_json_soporte
            query_insert_soporte = """
                INSERT INTO dbo.rips_datos_json_soporte 
                (resultState, procesoId, numFactura, codigoUnicoValidacion, fechaRadicacion, rutaArchivos, tipo_factura)
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            result_insert = conn.execute_query(
                query_insert_soporte, 
                (result_state, proceso_id, num_factura, codigo_unico_validacion, 
                 fecha_radicacion, ruta_archivos, tipo_factura),
                fetch_one=True
            )
            
            if not result_insert:
                print(f"[ERROR] Error insertando datos principales del JSON soporte para factura {num_factura}")
                return False
            
            datos_json_soporte_id = result_insert['id'] if result_insert else None
            
            if not datos_json_soporte_id:
                print(f"[ERROR] No se pudo obtener el ID insertado para factura {num_factura}")
                return False
            
            # 2. Insertar resultados de validación
            validaciones_insertadas = 0
            resultados_validacion = raw_data.get('ResultadosValidacion', [])
            
            for validacion in resultados_validacion:
                query_insert_validacion = """
                    INSERT INTO dbo.rips_json_soporte_resultado_validacion 
                    (datos_json_soporte_id, clase, codigo, descripcion, observaciones, path_fuente, fuente)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                
                conn.execute_query(
                    query_insert_validacion, 
                    (
                        datos_json_soporte_id,
                        validacion.get('Clase', ''),
                        validacion.get('Codigo', ''),
                        validacion.get('Descripcion', ''),
                        validacion.get('Observaciones', ''),
                        validacion.get('PathFuente', ''),
                        validacion.get('Fuente', '')
                    )
                )
                validaciones_insertadas += 1
            
            print(f"[OK] JSON soporte guardado para factura {num_factura}: {validaciones_insertadas} validaciones")
            return True
            
        except Exception as e:
            print(f"[ERROR] Error guardando JSON soporte para factura {num_factura}: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False
    
    def save_facturas_json(self, conn, num_factura, envio_ministerio_json, respuesta_ministerio_json, soporte_eps_json, tipo_factura='CAPITA'):
        """
        Guarda los JSON de facturación en la tabla rips_facturas_json
        
        Args:
            conn: Conexión a la base de datos SQL Server
            num_factura: Número de factura
            envio_ministerio_json: JSON completo enviado al ministerio (json_factura_capita)
            respuesta_ministerio_json: JSON de respuesta del ministerio (data_response)
            soporte_eps_json: JSON de soporte EPS (json_para_guardar de la estructura RIPS)
            tipo_factura: Tipo de factura (por defecto 'CAPITA')
        
        Returns:
            bool: True si se guardó exitosamente, False en caso contrario
        """
        try:
            import json
            
            # Convertir los diccionarios a JSON strings
            envio_str = json.dumps(envio_ministerio_json, ensure_ascii=False, default=str)
            respuesta_str = json.dumps(respuesta_ministerio_json, ensure_ascii=False, default=str)
            soporte_str = json.dumps(soporte_eps_json, ensure_ascii=False, default=str)
            
            # Verificar si ya existe un registro para esta factura Y tipo
            query_check = """
                SELECT id FROM dbo.rips_facturas_json 
                WHERE numFactura = ? AND tipo_factura = ?
            """
            existing = conn.execute_query(query_check, (num_factura, tipo_factura))
            
            if existing:
                # Si existe, actualizar
                query_update = """
                    UPDATE dbo.rips_facturas_json
                    SET envio_ministerio = ?,
                        respuesta_ministerio = ?,
                        soporte_eps = ?,
                        fecha_creacion = GETDATE()
                    WHERE numFactura = ? AND tipo_factura = ?
                """
                conn.execute_query(
                    query_update,
                    (envio_str, respuesta_str, soporte_str, num_factura, tipo_factura)
                )
                print(f"[OK] Registro actualizado en rips_facturas_json para factura {num_factura} tipo {tipo_factura}")
            else:
                # Si no existe, insertar
                query_insert = """
                    INSERT INTO dbo.rips_facturas_json 
                    (numFactura, envio_ministerio, respuesta_ministerio, soporte_eps, tipo_factura)
                    VALUES (?, ?, ?, ?, ?)
                """
                conn.execute_query(
                    query_insert,
                    (num_factura, envio_str, respuesta_str, soporte_str, tipo_factura)
                )
                print(f"[OK] Registro insertado en rips_facturas_json para factura {num_factura} tipo {tipo_factura}")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error guardando en rips_facturas_json para factura {num_factura}: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return False
        
    def _delete_existing_json_soporte_records(self, conn, num_factura, tipo_factura='FINAL'):
        """
        Elimina los registros existentes de JSON soporte para una factura específica y tipo.
        Esto evita duplicados cuando se reprocesa una factura.
        
        Args:
            conn: Conexión a la base de datos
            num_factura (str): Número de factura a limpiar
            tipo_factura (str): Tipo de factura a limpiar ('INICIAL' o 'FINAL')
            
        Returns:
            bool: True si la eliminación fue exitosa, False en caso contrario
        """
        try:
            # Primero eliminar las validaciones (por la restricción de clave foránea)
            query_delete_validaciones = """
                DELETE FROM dbo.rips_json_soporte_resultado_validacion 
                WHERE datos_json_soporte_id IN (
                    SELECT id FROM dbo.rips_datos_json_soporte 
                    WHERE [numFactura] = ? AND [tipo_factura] = ?
                )
            """
            validaciones_eliminadas = conn.execute_query(query_delete_validaciones, (num_factura, tipo_factura))
            
            # Luego eliminar el registro principal
            query_delete_soporte = """
                DELETE FROM dbo.rips_datos_json_soporte 
                WHERE [numFactura] = ? AND [tipo_factura] = ?
            """
            registros_eliminados = conn.execute_query(query_delete_soporte, (num_factura, tipo_factura))
            
            if validaciones_eliminadas > 0 or registros_eliminados > 0:
                print(f"[LIMPIEZA] Eliminados registros anteriores de factura {num_factura} tipo {tipo_factura}: {registros_eliminados} registro(s) principal(es), {validaciones_eliminadas} validación(es)")
            
            return True
            
        except Exception as e:
            print(f"[ATENCION] Error eliminando registros anteriores para factura {num_factura} tipo {tipo_factura}: {str(e)}")
            # No retornamos False porque esto no debe detener el proceso
            return False
        
        
