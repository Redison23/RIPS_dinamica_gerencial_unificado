# -*- coding: utf-8 -*-
"""
Scheduler para envio automatico de facturas EVENTO (tipo_factura = 'E').

Reemplaza al antiguo proyecto kirox-fevrips (servicio RipsSchedulerService) integrando
su unica funcionalidad propia dentro del proyecto unificado: cada N minutos (default 30)
busca las facturas EVENTO pendientes (sin CUV) de los ultimos 40 dias y las envia al
Ministerio reutilizando exactamente la misma ruta que el endpoint /ministerio/envio/fev-rips.
"""

import os
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

from sql_server_conn import SQLServerConnection, PostgreSQLConnection as PSQL
from RipsSender import RipsSender
from Utilities import Utilities as ut
from fev_rips_payload_utils import construir_payload_fev_rips_desde_num_factura

load_dotenv()

# Logger especifico para el scheduler de eventos
evento_logger = logging.getLogger("evento_scheduler")
evento_logger.setLevel(logging.INFO)
evento_logger.propagate = False

if not evento_logger.handlers:
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)

    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "evento_scheduler.log"),
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
    evento_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    evento_logger.addHandler(console_handler)


def _nueva_conexion_sql():
    return SQLServerConnection(
        server=os.getenv("DB_SERVER"),
        database=os.getenv("DB_DATABASE"),
        username=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        driver=os.getenv("DB_DRIVER")
    )


def _nueva_conexion_postgre():
    return PSQL(
        dbname=os.getenv("POSTGRES_DBNAME"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST")
    )


def _sender_autenticado():
    """Crea y autentica un RipsSender contra el API del Ministerio (mismo patron que la API)."""
    sender = RipsSender(base_url=os.getenv("MINISTERIO_API_URL"), timeout=300, verify_ssl=False)
    auth_result = sender.authenticate(
        os.getenv("MINISTERIO_TIPO_DOC"),
        os.getenv("MINISTERIO_NUM_DOC"),
        os.getenv("MINISTERIO_CLAVE"),
        os.getenv("MINISTERIO_NIT")
    )
    if not auth_result.get("success"):
        raise RuntimeError(f"Autenticacion con el ministerio fallida: {auth_result.get('error') or auth_result.get('message')}")
    return sender


def get_eventos_pendientes():
    """
    Facturas EVENTO pendientes de envio:
    - tipo_factura = 'E'
    - estado_registro = 'A'
    - numFactura no nulo
    - fecha_factura de los ultimos 40 dias
    - sin codigo_cuv (no aprobadas aun)
    """
    conn = _nueva_conexion_sql()
    try:
        if not conn.connect():
            evento_logger.error("No se pudo conectar a SQL Server para listar eventos pendientes")
            return []

        query = """
        SELECT DISTINCT AF.numFactura
        FROM dbo.rips_af AS AF
        WHERE AF.tipo_factura = 'E'
          AND AF.numFactura IS NOT NULL
          AND AF.estado_registro = 'A'
          AND AF.fecha_factura >= DATEADD(day, -40, GETDATE())
          AND (AF.codigo_cuv IS NULL OR AF.codigo_cuv = '' OR AF.codigo_cuv = 'NULL')
        ORDER BY AF.numFactura DESC
        """
        result = conn.execute_query(query)
        return [r['numFactura'] for r in result] if result else []
    except Exception as e:
        evento_logger.error(f"Error obteniendo eventos pendientes: {e}")
        return []
    finally:
        conn.close()


def enviar_evento_individual(num_factura: str) -> dict:
    """
    Envia una factura EVENTO al ministerio reutilizando la misma logica y persistencia
    que el endpoint /ministerio/envio/fev-rips.
    """
    evento_logger.info(f"[INICIO] Procesando evento: {num_factura}")

    conn_sql = None
    conn_postgre = None
    try:
        conn_sql = _nueva_conexion_sql()
        if not conn_sql.connect():
            return {'success': False, 'numFactura': num_factura, 'error': 'No se pudo conectar a SQL Server'}

        conn_postgre = _nueva_conexion_postgre()
        if not conn_postgre.connect():
            return {'success': False, 'numFactura': num_factura, 'error': 'No se pudo conectar a PostgreSQL'}

        # Construir payload (RIPS + XML base64) - misma utilidad que el endpoint
        payload = construir_payload_fev_rips_desde_num_factura(num_factura, conn_sql, conn_postgre)

        # Enviar al ministerio
        sender = _sender_autenticado()
        result = sender.send_paquete(
            payload_json=payload,
            tipo_paquete="FEV_RIPS",
            invoice_number=num_factura
        )

        # RVG18 se trata como exito operativo (factura ya reportada)
        if ut.tiene_error_rvg18(result):
            evento_logger.info(f"[INFO] Factura {num_factura} con RVG18 (ya reportada). Se marca exitosa.")
            result['success'] = True

        data_response = result.get("raw_response", {}).get("data", result.get("raw_response"))

        # Persistencia identica al endpoint
        sender.update_invoice_status(conn_sql, num_factura, result, tipo_cargue="INICIAL")
        codigo_retorno = "APROBADO" if result.get("success", False) else "RECHAZADO"
        conn_sql.execute_query(
            """
            UPDATE dbo.rips_af
            SET codigo_retorno = ?, fecha_retorno = ?
            WHERE [numFactura] = ?
            """,
            (codigo_retorno, datetime.now(), num_factura)
        )
        sender.save_json_soporte_to_db(conn_sql, result, num_factura, tipo_factura="EVENTO")
        sender.save_facturas_json(
            conn_sql,
            num_factura,
            payload,
            data_response,
            payload.get("rips", {}),
            "EVENTO"
        )

        if result.get("success", False):
            evento_logger.info(f"[EXITO] Evento {num_factura} enviado correctamente (CUV/{codigo_retorno})")
        else:
            evento_logger.warning(f"[FALLO] Evento {num_factura} rechazado. Errores: {result.get('errors', [])}")

        return {
            'success': result.get('success', False),
            'numFactura': num_factura,
            'codigo_retorno': codigo_retorno,
            'ministerio_response': data_response
        }

    except Exception as e:
        evento_logger.error(f"[ERROR] Excepcion procesando evento {num_factura}: {e}")
        return {'success': False, 'numFactura': num_factura, 'error': str(e)}
    finally:
        if conn_sql and getattr(conn_sql, "conn", None):
            try:
                conn_sql.close()
            except Exception:
                pass
        if conn_postgre and getattr(conn_postgre, "conn", None):
            try:
                conn_postgre.close()
            except Exception:
                pass


def job_enviar_eventos():
    """Job periodico: envia todas las facturas EVENTO pendientes."""
    evento_logger.info("=" * 70)
    evento_logger.info("INICIANDO ENVIO AUTOMATICO DE FACTURAS EVENTO")
    evento_logger.info(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    evento_logger.info("=" * 70)

    pendientes = get_eventos_pendientes()

    if not pendientes:
        evento_logger.info("No hay facturas EVENTO pendientes de envio")
        evento_logger.info("=" * 70)
        return

    evento_logger.info(f"Facturas EVENTO pendientes encontradas: {len(pendientes)}")

    exitosas = []
    fallidas = []

    for i, num_factura in enumerate(pendientes, 1):
        evento_logger.info(f"[{i}/{len(pendientes)}] Procesando: {num_factura}")
        resultado = enviar_evento_individual(num_factura)
        if resultado.get('success'):
            exitosas.append(num_factura)
        else:
            fallidas.append({'factura': num_factura, 'error': resultado.get('error', 'Rechazada o error')})

    evento_logger.info("=" * 70)
    evento_logger.info("RESUMEN DE ENVIO AUTOMATICO DE EVENTOS")
    evento_logger.info(f"Total procesadas: {len(pendientes)}")
    evento_logger.info(f"Exitosas: {len(exitosas)}")
    evento_logger.info(f"Fallidas: {len(fallidas)}")
    if fallidas:
        for f in fallidas:
            evento_logger.warning(f"  - {f['factura']}: {f['error']}")
    evento_logger.info("=" * 70)


# Instancia global del scheduler
_evento_scheduler = None


def init_evento_scheduler():
    """Inicializa el scheduler de envio automatico de eventos (cada N minutos)."""
    global _evento_scheduler

    if _evento_scheduler is not None:
        evento_logger.info("Scheduler de eventos ya esta inicializado")
        return _evento_scheduler

    try:
        intervalo = int(os.getenv("EVENTO_SCHEDULER_INTERVAL_MIN", "30"))
        if intervalo < 1:
            intervalo = 30
    except (TypeError, ValueError):
        intervalo = 30

    _evento_scheduler = BackgroundScheduler(timezone='America/Bogota')
    _evento_scheduler.add_job(
        job_enviar_eventos,
        IntervalTrigger(minutes=intervalo),
        id='envio_eventos',
        name='Envio automatico de facturas EVENTO',
        replace_existing=True,
        max_instances=1,   # nunca dos corridas en paralelo
        coalesce=True       # si se acumulan disparos, ejecutar solo una vez
    )
    _evento_scheduler.start()

    evento_logger.info("=" * 70)
    evento_logger.info("SCHEDULER DE EVENTOS INICIADO")
    evento_logger.info(f"Intervalo: cada {intervalo} minutos")
    evento_logger.info("Zona horaria: America/Bogota")
    evento_logger.info("=" * 70)

    return _evento_scheduler


def shutdown_evento_scheduler():
    """Detiene el scheduler de eventos de forma segura."""
    global _evento_scheduler
    if _evento_scheduler is not None:
        _evento_scheduler.shutdown(wait=False)
        _evento_scheduler = None
        evento_logger.info("Scheduler de eventos detenido correctamente")


def get_evento_scheduler_status():
    """Estado actual del scheduler de eventos."""
    global _evento_scheduler
    if _evento_scheduler is None:
        return {'running': False, 'jobs': []}

    jobs = []
    for job in _evento_scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run': str(job.next_run_time) if job.next_run_time else None,
            'trigger': str(job.trigger)
        })
    return {'running': _evento_scheduler.running, 'jobs': jobs}


if __name__ == "__main__":
    print("Ejecutando envio manual de eventos...")
    job_enviar_eventos()
