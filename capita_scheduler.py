# -*- coding: utf-8 -*-
"""
Scheduler para envío automático de Capitas Iniciales
Ejecuta diariamente a las 12:00 AM (medianoche)
"""

import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from sql_server_conn import SQLServerConnection, PostgreSQLConnection as PSQL
from EstructuraJson import EstructuraJsonRips
import RipsQueries as queries
import ToBase64 as b64
from RipsSender import RipsSender

load_dotenv()

# Logger específico para el scheduler
scheduler_logger = logging.getLogger("capita_scheduler")
scheduler_logger.setLevel(logging.INFO)
scheduler_logger.propagate = False

if not scheduler_logger.handlers:
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    from logging.handlers import TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "capita_scheduler.log"),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    scheduler_logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    scheduler_logger.addHandler(console_handler)


def tiene_error_rvg18(result):
    """Verifica si el resultado tiene error RVG18 (ya está reportada)"""
    if not result:
        return False

    # Estructura procesada por RipsSender.process_invoice_response
    for error in result.get('errors', []):
        if isinstance(error, dict) and str(error.get('code', '')).upper() == 'RVG18':
            return True

    raw_response = result.get('raw_response', result)
    if not isinstance(raw_response, dict):
        return False

    data = raw_response.get('data', raw_response)
    if not isinstance(data, dict):
        return False

    # Estructura principal devuelta por SISPRO
    for validacion in data.get('ResultadosValidacion', []):
        if isinstance(validacion, dict) and str(validacion.get('Codigo', '')).upper() == 'RVG18':
            return True

    # Fallback para estructuras alternas/legadas
    for error in data.get('errores', []):
        if isinstance(error, dict):
            codigo = error.get('codigo', error.get('Codigo', ''))
            if str(codigo).upper() == 'RVG18':
                return True

    return False


def get_capitas_pendientes():
    """
    Obtiene las facturas globales (capitas) que aún no han sido enviadas.
    
    Criterios:
    - tipo_factura = 'C' (Capita)
    - estado_registro = 'A' (Activo)
    - factura_global existe y no está vacía
    - La factura global NO tiene código CUV (buscando por numFactura de la global)
    - Solo facturas de los últimos 40 días
    """
    conn = SQLServerConnection(
        server=os.getenv('DB_SERVER'),
        database=os.getenv('DB_DATABASE'),
        username=os.getenv('DB_USERNAME'),
        password=os.getenv('DB_PASSWORD'),
        driver=os.getenv('DB_DRIVER')
    )
    
    try:
        conn.connect()
        
        # Obtener capitas pendientes de envío
        # La factura global debe existir como registro en rips_af y NO tener código CUV
        query = """
        SELECT DISTINCT AF.factura_global
        FROM rips_af AF
        INNER JOIN rips_af FG ON AF.factura_global = FG.numFactura
        WHERE AF.tipo_factura = 'C'
        AND AF.factura_global IS NOT NULL
        AND AF.factura_global != ''
        AND AF.estado_registro = 'A'
        AND AF.fecha_factura >= DATEADD(day, -40, GETDATE())
        AND (FG.codigo_cuv IS NULL OR FG.codigo_cuv = '' OR FG.codigo_cuv = 'NULL')
        ORDER BY AF.factura_global
        """
        
        result = conn.execute_query(query)
        return [r['factura_global'] for r in result]
        
    except Exception as e:
        scheduler_logger.error(f"Error obteniendo capitas pendientes: {e}")
        return []
    finally:
        conn.close()


def enviar_capita_inicial(factura_global: str) -> dict:
    """
    Envía una capita inicial al ministerio.
    
    Args:
        factura_global: Número de la factura global (capita)
        
    Returns:
        dict con el resultado del envío
    """
    scheduler_logger.info(f"[INICIO] Procesando capita: {factura_global}")
    
    conSqlServer = None
    connPostgre = None
    
    try:
        # Inicializar conexiones
        conSqlServer = SQLServerConnection(
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            server=os.getenv("DB_SERVER")
        )
        connPostgre = PSQL(
            dbname=os.getenv("POSTGRES_DBNAME"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST")
        )
        
        # Autenticar con el ministerio
        sender = RipsSender(base_url=os.getenv("MINISTERIO_API_URL"), timeout=300, verify_ssl=False)
        auth_result = sender.authenticate(
            os.getenv("MINISTERIO_TIPO_DOC"), 
            os.getenv("MINISTERIO_NUM_DOC"), 
            os.getenv("MINISTERIO_CLAVE"), 
            os.getenv("MINISTERIO_NIT")
        )
        
        if not auth_result['success']:
            scheduler_logger.error(f"[ERROR] Autenticación fallida para {factura_global}")
            return {'success': False, 'error': 'Error en autenticación con el ministerio'}
        
        # Crear estructura only_xml
        json_factura_capita = EstructuraJsonRips.only_xml()
        
        # Buscar XML de la factura global
        xml_data = None
        try:
            connPostgre.connect()
            datos_xml = queries.RipsQueries.get_datos_attached(connPostgre, factura_global)
            if datos_xml:
                xml_data = datos_xml[0].get('attached_document', "")
        except Exception as xml_error:
            scheduler_logger.error(f"[ERROR] Error obteniendo XML para {factura_global}: {xml_error}")
            return {'success': False, 'error': f'Error obteniendo XML: {str(xml_error)}'}
        finally:
            if connPostgre:
                connPostgre.close()
        
        if not xml_data:
            scheduler_logger.warning(f"[SKIP] No se encontró XML para {factura_global}")
            return {'success': False, 'error': 'No se encontró XML para la factura'}
        
        # Convertir a Base64
        base64_xml = b64.ToBase64.xml_texto_a_base64(xml_data)
        if not base64_xml:
            scheduler_logger.error(f"[ERROR] Error convirtiendo XML a Base64 para {factura_global}")
            return {'success': False, 'error': 'Error convirtiendo XML a Base64'}
        
        json_factura_capita["xmlFevFile"] = base64_xml
        scheduler_logger.info(f"[OK] XML convertido a Base64 para {factura_global}")
        
        # Enviar al ministerio
        scheduler_logger.info(f"[ENVIO] Enviando capita inicial: {factura_global}")
        result = sender.send_invoice(json_factura_capita, tipo_cargue='INICIAL')
        
        # Verificar RVG18 (ya está reportada)
        if tiene_error_rvg18(result):
            scheduler_logger.info(f"[INFO] Factura {factura_global} tiene error RVG18 (ya reportada). Se marca como exitosa.")
            result['success'] = True
        
        # Actualizar estado en BD
        conSqlServer.connect()
        update_success = sender.update_invoice_status(conSqlServer, factura_global, result, tipo_cargue='INICIAL')
        
        # Guardar JSON soporte
        json_soporte_success = sender.save_json_soporte_to_db(conSqlServer, result, factura_global, tipo_factura='INICIAL')
        
        # Guardar en rips_facturas_json
        raw_response = result.get('raw_response', result)
        data_response = raw_response.get('data', raw_response)
        facturas_json_success = sender.save_facturas_json(
            conSqlServer, 
            factura_global, 
            json_factura_capita,
            data_response,
            {"xmlFevFile": json_factura_capita.get("xmlFevFile", "")},
            'INICIAL'
        )
        
        if result.get('success', False):
            scheduler_logger.info(f"[EXITO] Capita {factura_global} enviada correctamente")
        else:
            scheduler_logger.warning(f"[FALLO] Capita {factura_global} no pudo ser enviada: {result}")
        
        return {
            'success': result.get('success', False),
            'factura_global': factura_global,
            'tipo_cargue': 'INICIAL',
            'ministerio_response': data_response
        }
        
    except Exception as e:
        scheduler_logger.error(f"[ERROR] Excepción procesando capita {factura_global}: {e}")
        return {'success': False, 'factura_global': factura_global, 'error': str(e)}
    finally:
        if conSqlServer:
            try:
                conSqlServer.close()
            except:
                pass


def job_enviar_capitas_iniciales():
    """
    Job que se ejecuta diariamente para enviar todas las capitas iniciales pendientes.
    """
    scheduler_logger.info("=" * 70)
    scheduler_logger.info("INICIANDO ENVÍO AUTOMÁTICO DE CAPITAS INICIALES")
    scheduler_logger.info(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    scheduler_logger.info("=" * 70)
    
    # Obtener capitas pendientes
    capitas_pendientes = get_capitas_pendientes()
    
    if not capitas_pendientes:
        scheduler_logger.info("No hay capitas pendientes de envío")
        scheduler_logger.info("=" * 70)
        return
    
    scheduler_logger.info(f"Capitas pendientes encontradas: {len(capitas_pendientes)}")
    
    # Resultados
    exitosas = []
    fallidas = []
    
    # Procesar cada capita
    for i, factura_global in enumerate(capitas_pendientes, 1):
        scheduler_logger.info(f"[{i}/{len(capitas_pendientes)}] Procesando: {factura_global}")
        
        resultado = enviar_capita_inicial(factura_global)
        
        if resultado.get('success'):
            exitosas.append(factura_global)
        else:
            fallidas.append({'factura': factura_global, 'error': resultado.get('error', 'Error desconocido')})
    
    # Resumen
    scheduler_logger.info("=" * 70)
    scheduler_logger.info("RESUMEN DE ENVÍO AUTOMÁTICO DE CAPITAS")
    scheduler_logger.info(f"Total procesadas: {len(capitas_pendientes)}")
    scheduler_logger.info(f"Exitosas: {len(exitosas)}")
    scheduler_logger.info(f"Fallidas: {len(fallidas)}")
    
    if fallidas:
        scheduler_logger.warning("Capitas fallidas:")
        for f in fallidas:
            scheduler_logger.warning(f"  - {f['factura']}: {f['error']}")
    
    scheduler_logger.info("=" * 70)


# Instancia del scheduler (global)
_scheduler = None


def init_scheduler():
    """
    Inicializa el scheduler para envío automático de capitas.
    Se ejecuta diariamente a la 1:05 AM.
    """
    global _scheduler
    
    if _scheduler is not None:
        scheduler_logger.info("Scheduler ya está inicializado")
        return _scheduler
    
    _scheduler = BackgroundScheduler(timezone='America/Bogota')
    
    # Programar el job para la 1:05 AM todos los días
    _scheduler.add_job(
        job_enviar_capitas_iniciales,
        CronTrigger(hour=1, minute=5),  # 01:05 AM
        id='envio_capitas_iniciales',
        name='Envío automático de capitas iniciales',
        replace_existing=True
    )
    
    _scheduler.start()
    
    scheduler_logger.info("=" * 70)
    scheduler_logger.info("SCHEDULER DE CAPITAS INICIADO")
    scheduler_logger.info("Horario programado: Diariamente a la 1:05 AM")
    scheduler_logger.info("Zona horaria: America/Bogota")
    scheduler_logger.info("=" * 70)
    
    return _scheduler


def shutdown_scheduler():
    """Detiene el scheduler de forma segura."""
    global _scheduler
    
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        scheduler_logger.info("Scheduler detenido correctamente")


def get_scheduler_status():
    """Obtiene el estado actual del scheduler."""
    global _scheduler
    
    if _scheduler is None:
        return {
            'running': False,
            'jobs': []
        }
    
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': str(job.next_run_time) if job.next_run_time else None,
            'trigger': str(job.trigger)
        })
    
    return {
        'running': _scheduler.running,
        'jobs': jobs
    }


def ejecutar_envio_manual():
    """
    Ejecuta el envío de capitas de forma manual (para pruebas o ejecución forzada).
    """
    scheduler_logger.info("Ejecución manual de envío de capitas solicitada")
    job_enviar_capitas_iniciales()


if __name__ == "__main__":
    # Si se ejecuta directamente, hacer una prueba
    print("Ejecutando envío manual de capitas...")
    ejecutar_envio_manual()
