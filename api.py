# -*- coding: utf-8 -*-
"""
API Unificada - Hospital Sagrado Corazon de Jesus de Quimbaya
Integra funcionalidades de:
1. Exposicion de tablas RIPS para Odoo
2. Envio de facturas CAPITA al Ministerio de Salud
3. Envio automatico de Capitas Iniciales (programado diariamente a las 12:00 AM)
"""

from fastapi import FastAPI, HTTPException, Query, Path, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
import uvicorn
from dotenv import load_dotenv
from sql_server_conn import SQLServerConnection, PostgreSQLConnection as PSQL
from Utilities import Utilities as ut

# Cargar variables de entorno
load_dotenv()
from EstructuraJson import EstructuraJsonRips
import RipsQueries as queries
import Utilities as b64
from RipsSender import RipsSender
from capita_scheduler import init_scheduler, shutdown_scheduler, get_scheduler_status, ejecutar_envio_manual, get_capitas_pendientes
import warnings
import json
import re
import pandas as pd
from datetime import datetime, date
from collections import OrderedDict
from contextlib import asynccontextmanager
import logging
import os
from logging.handlers import TimedRotatingFileHandler
from fev_rips_payload_utils import (
    validar_estructura_fev_rips_payload,
    construir_payload_fev_rips_desde_num_factura,
)
from models.request_models import (
    NotificacionesEventoRequest,
    EnvioCapitaRequest,
    EnvioMinisterioFevRipsRequest,
    ObtenerJsonRequest,
    NotificacionesCapitaRequest,
)

# Ignorar advertencias de certificados SSL (solo en desarrollo)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Configurar logging
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "api.log")

# Configurar el logger
logger = logging.getLogger("api_unificada")
logger.setLevel(logging.INFO)
logger.propagate = False  # Evitar duplicacion de logs

# Evitar agregar handlers duplicados si el modulo se recarga
if not logger.handlers:
    # Handler para archivo (rotacion diaria, retencion 30 dias)
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setLevel(logging.INFO)

    # Formato del log
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Tambien log a consola
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manejo de ciclo de vida de la aplicacion (startup/shutdown)."""
    try:
        logger.info("=" * 70)
        logger.info("Iniciando API Unificada - Hospital Sagrado Corazon de Jesus")
        logger.info("=" * 70)
        ut.configure_threadpool(logger)
        db = ut.get_db_connection()
        db.close()
        print(f"[OK] API unificada iniciada en http://{os.getenv('API_HOST', '0.0.0.0')}:{int(os.getenv('API_PORT', '8000'))}")
        print(f"[OK] Documentacion disponible en http://{os.getenv('API_HOST', '0.0.0.0')}:{int(os.getenv('API_PORT', '8000'))}/docs")
    except Exception as e:
        print(f"[WARN] No se pudo conectar a la base de datos al iniciar: {e}")
        print("  La API intentara reconectar en cada peticion")

    try:
        init_scheduler()
        print("[OK] Scheduler de capitas iniciales activado")
    except Exception as e:
        print(f"[WARN] Error iniciando scheduler de capitas: {e}")

    try:
        yield
    finally:
        try:
            shutdown_scheduler()
            print("[OK] Scheduler de capitas detenido")
        except Exception as e:
            print(f"[WARN] Error deteniendo scheduler: {e}")

# Crear instancia de FastAPI
app = FastAPI(
    title="API Unificada - Hospital Sagrado Corazon de Jesus",
    version="2.0.0",
    description="API unificada para exposicion de datos RIPS y envio de facturas CAPITA",
    lifespan=lifespan
)

# Agregar middleware de logging
from logging_middleware import log_requests_middleware
app.middleware("http")(log_requests_middleware)

# Configurar CORS
allowed_origins = os.getenv("API_ALLOWED_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins.split(",") if allowed_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_ministerio_sender_autenticado():
    """Crea y autentica un cliente RipsSender para consumir el API del Ministerio."""
    sender = RipsSender(base_url=os.getenv("MINISTERIO_API_URL"), timeout=300, verify_ssl=False)
    auth_result = sender.authenticate(
        os.getenv("MINISTERIO_TIPO_DOC"),
        os.getenv("MINISTERIO_NUM_DOC"),
        os.getenv("MINISTERIO_CLAVE"),
        os.getenv("MINISTERIO_NIT")
    )
    if not auth_result.get("success"):
        raise HTTPException(status_code=500, detail='Error en autenticacion con el ministerio')
    return sender

# =============================================================================
# ENDPOINTS DE INFORMACION GENERAL
# =============================================================================

@app.get("/", tags=["Info"])
def root():
    """Endpoint raiz con informacion de la API unificada"""
    return {
        "message": "API Unificada - Hospital Sagrado Corazon de Jesus de Quimbaya",
        "version": "2.0.0",
        "database": os.getenv("DB_DATABASE"),
        "docs": "/docs",
        "modulos": {
            "rips_consulta": "Consulta de datos RIPS para Odoo",
            "ministerio_envio": "Envio de facturas MINISTERIO DE SALUD"
        },
        "endpoints": {
            "consulta_rips": {
                "factura": "/rips_facturas_json/factura/{num_factura}",
                "estado": "/rips_af/estado/{num_factura}",
                "por_fecha": "/facturas/por-fecha",
                "avanzado": "/facturas/avanzado",
                "agrupaciones": "/facturas/agrupaciones",
                "notificaciones": "/facturas/notificaciones-evento"
            },
            "capita": {
                "envio_inicial": "/capita/envio-inicial",
                "envio_final": "/capita/envio-final",
                "envio_periodo": "/envio/capita-periodo",
                "obtener_json": "/capita/obtener-json",
                "notificaciones": "/capita/notificaciones",
                "codigos_cuv": "/capita/codigos-cuv"
            },
            "scheduler_capita": {
                "status": "/capita/scheduler/status",
                "pendientes": "/capita/scheduler/pendientes",
                "ejecutar_ahora": "/capita/scheduler/ejecutar-ahora"
            },
            "ministerio": {
                "fev_rips": "/ministerio/envio/fev-rips"
            },
            "sistema": "/health"
        }
    }

@app.get("/health", tags=["Info"])
def health_check():
    """Verifica estado de BD y disponibilidad de envio al Ministerio (login SISPRO)."""
    timestamp = datetime.now().isoformat()

    # -------- Check Base de Datos --------
    db = None
    db_connected = False
    db_test_query = None
    db_error = None
    try:
        db = ut.get_db_connection()
        db_test_query = db.execute_query("SELECT 1 as test", fetch_one=True)
        db_connected = True
    except Exception as e:
        db_error = str(e)
    finally:
        if db and getattr(db, "conn", None):
            db.close()

    # -------- Check Ministerio (autenticacion) --------
    ministerio_available = False
    ministerio_error = None
    ministerio_message = None
    ministerio_url = os.getenv("MINISTERIO_API_URL")
    ministerio_timeout = int(os.getenv("MINISTERIO_HEALTH_TIMEOUT", "20"))

    required_envs = {
        "MINISTERIO_API_URL": ministerio_url,
        "MINISTERIO_TIPO_DOC": os.getenv("MINISTERIO_TIPO_DOC"),
        "MINISTERIO_NUM_DOC": os.getenv("MINISTERIO_NUM_DOC"),
        "MINISTERIO_CLAVE": os.getenv("MINISTERIO_CLAVE"),
        "MINISTERIO_NIT": os.getenv("MINISTERIO_NIT")
    }
    missing_envs = [key for key, value in required_envs.items() if not value]

    if missing_envs:
        ministerio_error = f"Faltan variables de entorno para Ministerio: {', '.join(missing_envs)}"
    else:
        try:
            sender = RipsSender(
                base_url=ministerio_url,
                timeout=ministerio_timeout,
                verify_ssl=False
            )
            auth_result = sender.authenticate(
                required_envs["MINISTERIO_TIPO_DOC"],
                required_envs["MINISTERIO_NUM_DOC"],
                required_envs["MINISTERIO_CLAVE"],
                required_envs["MINISTERIO_NIT"]
            )
            ministerio_available = bool(auth_result.get("success"))
            ministerio_message = auth_result.get("message")
            if not ministerio_available:
                ministerio_error = str(auth_result.get("error") or auth_result.get("message") or "Fallo autenticando con Ministerio")
        except Exception as e:
            ministerio_error = str(e)

    # -------- Estado global --------
    if db_connected and ministerio_available:
        overall_status = "healthy"
    elif db_connected or ministerio_available:
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return {
        "status": overall_status,
        "timestamp": timestamp,
        "database": "connected" if db_connected else "disconnected",
        "ministerio_envio": "available" if ministerio_available else "unavailable",
        "envio_disponible": ministerio_available,
        "checks": {
            "database": {
                "ok": db_connected,
                "test_query": db_test_query,
                "error": db_error
            },
            "ministerio": {
                "ok": ministerio_available,
                "url": ministerio_url,
                "timeout_seconds": ministerio_timeout,
                "message": ministerio_message,
                "error": ministerio_error
            }
        }
    }


# =============================================================================
# ENDPOINTS DE CONSULTA RIPS (para Odoo)
# =============================================================================

@app.get("/rips_facturas_json/factura/{num_factura}", tags=["Consulta RIPS"])
def get_factura_by_number(
    num_factura: str = Path(..., description="Numero de factura a buscar")
):
    """Obtiene los campos envio_ministerio, respuesta_ministerio y soporte_eps de una factura especfica"""
    db = None
    try:
        db = ut.get_db_connection()
        
        query = """
        SELECT [envio_ministerio], [respuesta_ministerio], [soporte_eps]
        FROM [dbo].[rips_facturas_json]
        WHERE [numFactura] = ?
        """
        
        data = db.execute_query(query, (num_factura,))
        
        if not data:
            raise HTTPException(status_code=404, detail=f"No se encontro factura con numero: {num_factura}")
        
        if len(data) == 1:
            return {
                "numFactura": num_factura,
                "found": True,
                "data": data[0]
            }
        else:
            return {
                "numFactura": num_factura,
                "found": True,
                "count": len(data),
                "data": data
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error buscando factura: {str(e)}")
    finally:
        if db and getattr(db, "conn", None):
            db.close()

@app.get("/rips_af/estado/{num_factura}", tags=["Consulta RIPS"])
def get_estado_factura_af(
    num_factura: str = Path(..., description="Numero de factura a consultar")
):
    """
    Obtiene el estado de aprobacin de una factura segn la tabla rips_af.
    Devuelve si est: APROBADO (con CUV), RECHAZADO o NO_ENVIADO
    """
    # Bloquear facturas que comiencen con "NO"
    if num_factura.upper().startswith("NO"):
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de factura no vlido: {num_factura}. Las facturas que comienzan con 'NO' no son procesadas."
        )
    
    db = None
    try:
        db = ut.get_db_connection()
        
        query = """
        SELECT [codigo_retorno], [codigo_cuv]
        FROM [dbo].[rips_af]
        WHERE [numFactura] = ?
        """
        
        data = db.execute_query(query, (num_factura,))
        
        if not data:
            raise HTTPException(
                status_code=404, 
                detail=f"No se encontro la factura {num_factura} en rips_af"
            )
        
        registro = data[0]
        codigo_retorno = registro.get('codigo_retorno', '').strip() if registro.get('codigo_retorno') else ''
        codigo_cuv = registro.get('codigo_cuv', '').strip() if registro.get('codigo_cuv') else ''
        
        if codigo_retorno.upper() == "RECHAZADO":
            estado = "RECHAZADO"
            descripcion = "La factura fue rechazada por el ministerio de salud"
        elif codigo_retorno.upper() == "APROBADO" and codigo_cuv:
            estado = "APROBADO"
            descripcion = "La factura fue aprobada por el ministerio de salud"
        elif not codigo_retorno and not codigo_cuv:
            estado = "NO_ENVIADO"
            descripcion = "La factura no ha sido enviada al ministerio"
        else:
            estado = "DESCONOCIDO"
            descripcion = f"Estado inconsistente - Retorno: {codigo_retorno}, CUV: {'Presente' if codigo_cuv else 'Vaco'}"
        
        return {
            "numFactura": num_factura,
            "estado": estado,
            "descripcion": descripcion,
            "codigo_retorno": codigo_retorno if codigo_retorno else None,
            "codigo_cuv": codigo_cuv if codigo_cuv else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando estado: {str(e)}")
    finally:
        if db and getattr(db, "conn", None):
            db.close()

def _normalizar_rango_fechas(fecha_inicio: str, fecha_fin: str) -> tuple[date, date]:
    """Valida formato YYYY-MM-DD y retorna objetos date para filtros SQL."""
    try:
        fecha_inicio_date = datetime.strptime(fecha_inicio.strip(), "%Y-%m-%d").date()
        fecha_fin_date = datetime.strptime(fecha_fin.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="fecha_inicio y fecha_fin deben tener formato YYYY-MM-DD"
        )

    if fecha_inicio_date > fecha_fin_date:
        raise HTTPException(
            status_code=400,
            detail="fecha_inicio no puede ser mayor que fecha_fin"
        )

    return fecha_inicio_date, fecha_fin_date

@app.get("/facturas/por-fecha", tags=["Consulta RIPS"])
def get_facturas_por_fecha(
    fecha_inicio: str = Query(..., description="Fecha inicial (formato: YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha final (formato: YYYY-MM-DD)"),
    limit: int = Query(1000, ge=1, le=10000, description="Numero maximo de registros"),
    solo_aprobadas_con_cuv: bool = Query(
        True,
        description="Si es True, retorna solo facturas EVENTO aprobadas y con cdigo CUV"
    )
):
    """
    Obtiene facturas con JOIN entre rips_af y rips_facturas_json filtradas por rango de fechas.
    """
    db = None
    try:
        db = ut.get_db_connection()
        fecha_inicio_date, fecha_fin_date = _normalizar_rango_fechas(fecha_inicio, fecha_fin)
        
        query = f"""
        SELECT DISTINCT TOP {limit}
            AF.numFactura,
            AF.fecha_factura,
            AF.codigo_retorno,
            AF.codigo_cuv,
            NULLIF(LTRIM(RTRIM(AF.codigo_cuv)), '') AS codigo_cuv_final,
            JS.envio_ministerio, 
            JS.respuesta_ministerio, 
            JS.soporte_eps, 
            CASE
                WHEN JS.tipo_factura IS NOT NULL THEN JS.tipo_factura
                WHEN UPPER(LTRIM(RTRIM(ISNULL(AF.tipo_factura, '')))) = 'E' THEN 'EVENTO'
                ELSE UPPER(LTRIM(RTRIM(ISNULL(AF.tipo_factura, ''))))
            END AS tipo_factura
        FROM (
            SELECT
                numFactura,
                fecha_factura,
                codigo_retorno,
                codigo_cuv,
                tipo_factura,
                estado_registro,
                CASE
                    WHEN LEN(CAST(fecha_factura AS NVARCHAR(50))) >= 10
                         AND SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 5, 1) = '-'
                         AND SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 8, 1) = '-'
                         AND ISDATE(
                             SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 9, 2) + '/' +
                             SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 6, 2) + '/' +
                             SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 1, 4)
                         ) = 1
                        THEN CONVERT(date, LEFT(CAST(fecha_factura AS NVARCHAR(50)), 10), 23)
                    WHEN ISDATE(CAST(fecha_factura AS NVARCHAR(50))) = 1
                        THEN CAST(CAST(fecha_factura AS NVARCHAR(50)) AS date)
                    ELSE NULL
                END AS fecha_factura_dt
            FROM [dbo].[rips_af]
            WHERE estado_registro != 'F'
        ) AS AF
        LEFT JOIN [dbo].[rips_facturas_json] AS JS
            ON JS.numFactura = AF.numFactura
           AND JS.tipo_factura = 'EVENTO'
        WHERE AF.fecha_factura_dt >= ? AND AF.fecha_factura_dt < DATEADD(DAY, 1, ?)
          AND (
                UPPER(LTRIM(RTRIM(ISNULL(AF.tipo_factura, '')))) IN ('E', 'EVENTO')
                OR JS.numFactura IS NOT NULL
              )
        """

        if solo_aprobadas_con_cuv:
            query += """
            AND UPPER(LTRIM(RTRIM(ISNULL(AF.codigo_retorno, '')))) = 'APROBADO'
            AND NULLIF(LTRIM(RTRIM(AF.codigo_cuv)), '') IS NOT NULL
            """

        query += " ORDER BY AF.fecha_factura DESC"
        
        data = db.execute_query(query, (fecha_inicio_date, fecha_fin_date))
        
        return {
            "fecha_inicio": fecha_inicio_date.isoformat(),
            "fecha_fin": fecha_fin_date.isoformat(),
            "solo_aprobadas_con_cuv": solo_aprobadas_con_cuv,
            "total_registros": len(data),
            "facturas": data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando facturas: {str(e)}")
    finally:
        if db and getattr(db, "conn", None):
            db.close()

@app.get("/facturas/avanzado", tags=["Consulta RIPS"])
def get_facturas_filtro_avanzado(
    fecha_inicio: str = Query(..., description="Fecha inicial (formato: YYYY-MM-DD)"),
    fecha_fin: str = Query(..., description="Fecha final (formato: YYYY-MM-DD)"),
    entidad: Optional[str] = Query(None, description="Nombre de la entidad para filtrar"),
    contrato: Optional[str] = Query(None, description="Contrato completo concatenado para filtrar"),
    tipo_entidad: Optional[str] = Query(None, description="Tipo de entidad"),
    limit: Optional[int] = Query(None, ge=1, description="Numero maximo de registros (opcional, sin limite si no se especifica)"),
    solo_aprobadas_con_cuv: bool = Query(
        True,
        description="Si es True, retorna solo facturas EVENTO aprobadas y con cdigo CUV"
    )
):
    """
    Obtiene facturas con filtros avanzados incluyendo JOIN con Hscj_Factura_Generacion.
    """
    db = None
    try:
        db = ut.get_db_connection()
        fecha_inicio_date, fecha_fin_date = _normalizar_rango_fechas(fecha_inicio, fecha_fin)
        
        # Construir SELECT con o sin TOP segn el limite
        if limit:
            select_clause = f"SELECT DISTINCT TOP {limit}"
        else:
            select_clause = "SELECT DISTINCT"
        
        query_base = f"""
        {select_clause}
            AF.numFactura,
            AF.fecha_factura,
            AF.codigo_retorno,
            AF.codigo_cuv,
            NULLIF(LTRIM(RTRIM(AF.codigo_cuv)), '') AS codigo_cuv_final,
            COALESCE(
                NULLIF(LTRIM(RTRIM(AF.entidad)), ''),
                NULLIF(LTRIM(RTRIM(FG.Entidad)), '')
            ) AS Entidad,
            CONCAT(
                ISNULL(NULLIF(LTRIM(RTRIM(AF.codigo_contrato)), ''), ISNULL(FG.Codigo_Contrato, '')),
                ' - ',
                ISNULL(NULLIF(LTRIM(RTRIM(AF.Contrato)), ''), ISNULL(FG.Contrato, ''))
            ) AS Contrato,
            FG.Tipo_Entidad,
            JS.envio_ministerio, 
            JS.respuesta_ministerio, 
            JS.soporte_eps, 
            CASE
                WHEN JS.tipo_factura IS NOT NULL THEN JS.tipo_factura
                WHEN UPPER(LTRIM(RTRIM(ISNULL(AF.tipo_factura, '')))) = 'E' THEN 'EVENTO'
                ELSE UPPER(LTRIM(RTRIM(ISNULL(AF.tipo_factura, ''))))
            END AS tipo_factura
        FROM (
            SELECT
                numFactura,
                fecha_factura,
                codigo_retorno,
                codigo_cuv,
                entidad,
                codigo_contrato,
                Contrato,
                tipo_factura,
                estado_registro,
                CASE
                    WHEN LEN(CAST(fecha_factura AS NVARCHAR(50))) >= 10
                         AND SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 5, 1) = '-'
                         AND SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 8, 1) = '-'
                         AND ISDATE(
                             SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 9, 2) + '/' +
                             SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 6, 2) + '/' +
                             SUBSTRING(CAST(fecha_factura AS NVARCHAR(50)), 1, 4)
                         ) = 1
                        THEN CONVERT(date, LEFT(CAST(fecha_factura AS NVARCHAR(50)), 10), 23)
                    WHEN ISDATE(CAST(fecha_factura AS NVARCHAR(50))) = 1
                        THEN CAST(CAST(fecha_factura AS NVARCHAR(50)) AS date)
                    ELSE NULL
                END AS fecha_factura_dt
            FROM [dbo].[rips_af]
            WHERE estado_registro != 'F'
        ) AS AF
        LEFT JOIN [Hospital].[dbo].[Hscj_Factura_Generacion] AS FG
            ON FG.Factura = AF.numFactura
        LEFT JOIN [dbo].[rips_facturas_json] AS JS
            ON JS.numFactura = AF.numFactura
           AND JS.tipo_factura = 'EVENTO'
        WHERE AF.fecha_factura_dt >= ? AND AF.fecha_factura_dt < DATEADD(DAY, 1, ?)
          AND (
                UPPER(LTRIM(RTRIM(ISNULL(AF.tipo_factura, '')))) IN ('E', 'EVENTO')
                OR JS.numFactura IS NOT NULL
              )
        """
        params = [fecha_inicio_date, fecha_fin_date]

        if solo_aprobadas_con_cuv:
            query_base += """
            AND UPPER(LTRIM(RTRIM(ISNULL(AF.codigo_retorno, '')))) = 'APROBADO'
            AND NULLIF(LTRIM(RTRIM(AF.codigo_cuv)), '') IS NOT NULL
            """
        
        if entidad:
            query_base += """
            AND COALESCE(
                NULLIF(LTRIM(RTRIM(AF.entidad)), ''),
                NULLIF(LTRIM(RTRIM(FG.Entidad)), '')
            ) LIKE ?
            """
            params.append(f"%{entidad}%")
        
        if contrato:
            contrato = contrato.strip()
            contrato_codigo_match = re.match(r"^\s*(\d+)\s*(?:-|$)", contrato)
            if contrato_codigo_match:
                # Si llega "1015001" o "1015001 - NOMBRE", filtra solo por codigo numerico.
                query_base += """
                AND (
                    LTRIM(RTRIM(AF.codigo_contrato)) = LTRIM(RTRIM(?))
                    OR LTRIM(RTRIM(FG.Codigo_Contrato)) = LTRIM(RTRIM(?))
                )
                """
                codigo = contrato_codigo_match.group(1)
                params.extend([codigo, codigo])
            else:
                # Codigo no numerico (ej: "01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO")
                # Extraer la parte del codigo antes del " - " y buscar en ambas tablas.
                contrato_code_name_match = re.match(r"^\s*(.+?)\s+-\s+(.+)$", contrato)
                if contrato_code_name_match:
                    codigo = contrato_code_name_match.group(1).strip()
                    query_base += """
                    AND (
                        LTRIM(RTRIM(AF.codigo_contrato)) = LTRIM(RTRIM(?))
                        OR LTRIM(RTRIM(FG.Codigo_Contrato)) = LTRIM(RTRIM(?))
                    )
                    """
                    params.extend([codigo, codigo])
                else:
                    # Codigo suelto sin " - " (ej: "01_EVN_890001006")
                    query_base += """
                    AND (
                        LTRIM(RTRIM(AF.codigo_contrato)) = LTRIM(RTRIM(?))
                        OR LTRIM(RTRIM(FG.Codigo_Contrato)) = LTRIM(RTRIM(?))
                    )
                    """
                    params.extend([contrato, contrato])
        
        if tipo_entidad:
            query_base += " AND FG.Tipo_Entidad = ?"
            params.append(tipo_entidad)
        
        query_base += " ORDER BY AF.fecha_factura DESC"
        
        data = db.execute_query(query_base, tuple(params))
        
        return {
            "fecha_inicio": fecha_inicio_date.isoformat(),
            "fecha_fin": fecha_fin_date.isoformat(),
            "filtros_aplicados": {
                "entidad": entidad,
                "contrato": contrato,
                "tipo_entidad": tipo_entidad,
                "limit": limit,
                "solo_aprobadas_con_cuv": solo_aprobadas_con_cuv
            },
            "total_registros": len(data),
            "facturas": data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando facturas: {str(e)}")
    finally:
        if db and getattr(db, "conn", None):
            db.close()

@app.get("/facturas/agrupaciones", tags=["Consulta RIPS"])
def get_agrupaciones_facturacion():
    """
    Obtiene datos agrupados de Hscj_Factura_Generacion para aplicar filtros.
    """
    db = None
    try:
        db = ut.get_db_connection()
        
        query_entidades = """
        SELECT Entidad
        FROM [Hospital].[dbo].[Hscj_Factura_Generacion]
        WHERE Entidad IS NOT NULL AND Entidad != ''
        GROUP BY Entidad
        ORDER BY Entidad
        """
        entidades = db.execute_query(query_entidades)
        
        query_contratos = """
        SELECT CONCAT(ISNULL(Codigo_Contrato, ''), ' - ', ISNULL(Contrato, '')) as contrato_completo
        FROM [Hospital].[dbo].[Hscj_Factura_Generacion]
        WHERE Contrato IS NOT NULL AND Contrato != ''
        GROUP BY Codigo_Contrato, Contrato
        ORDER BY contrato_completo
        """
        contratos = db.execute_query(query_contratos)
        
        query_tipos = """
        SELECT Tipo_Entidad
        FROM [Hospital].[dbo].[Hscj_Factura_Generacion]
        WHERE Tipo_Entidad IS NOT NULL AND Tipo_Entidad != ''
        GROUP BY Tipo_Entidad
        ORDER BY Tipo_Entidad
        """
        tipos_entidad = db.execute_query(query_tipos)
        
        return {
            "entidades": {
                "total_grupos": len(entidades),
                "datos": entidades
            },
            "contratos": {
                "total_grupos": len(contratos),
                "datos": contratos
            },
            "tipos_entidad": {
                "total_grupos": len(tipos_entidad),
                "datos": tipos_entidad
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo agrupaciones: {str(e)}")
    finally:
        if db and getattr(db, "conn", None):
            db.close()

@app.post("/facturas/notificaciones-evento", tags=["Consulta RIPS"])
def get_notificaciones_evento(
    request: NotificacionesEventoRequest = Body(...)
):
    """
    Obtiene las notificaciones/validaciones de una factura especfica de tipo EVENTO.
    """
    # Bloquear facturas que comiencen con "NO"
    if request.num_factura.upper().startswith("NO"):
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de factura no vlido: {request.num_factura}. Las facturas que comienzan con 'NO' no son procesadas."
        )
    
    db = None
    try:
        db = ut.get_db_connection()
        
        query = """
        SELECT
            DJS.id,
            DJS.numfactura,
            DJS.resultstate,
            DJS.procesoid,
            CAST(DJS.codigounicovalidacion AS NVARCHAR(MAX)) as codigounicovalidacion,
            CONVERT(VARCHAR(23), DJS.fecharadicacion, 121) as fecharadicacion,
            CAST(DJS.rutaarchivos AS NVARCHAR(MAX)) as rutaarchivos,
            DJS.tipo_factura,
            JSRV.id as validacion_id,
            JSRV.clase,
            JSRV.codigo,
            CAST(JSRV.descripcion AS NVARCHAR(MAX)) as descripcion,
            CAST(JSRV.observaciones AS NVARCHAR(MAX)) as observaciones,
            CAST(JSRV.path_fuente AS NVARCHAR(MAX)) as path_fuente,
            CAST(JSRV.fuente AS NVARCHAR(MAX)) as fuente
        FROM [Hospital].[dbo].[rips_datos_json_soporte] AS DJS
        LEFT JOIN [Hospital].[dbo].[rips_json_soporte_resultado_validacion] AS JSRV 
            ON DJS.id = JSRV.datos_json_soporte_id
        WHERE DJS.tipo_factura = 'EVENTO'
        AND DJS.numfactura = ?
        ORDER BY JSRV.id
        """
        
        data = db.execute_query(query, (request.num_factura,))
        
        if not data:
            raise HTTPException(
                status_code=404, 
                detail=f"No se encontro factura tipo EVENTO con numero: {request.num_factura}"
            )
        
        factura_data = {
            "id": data[0]['id'],
            "numfactura": data[0]['numfactura'],
            "resultstate": data[0]['resultstate'],
            "procesoid": data[0]['procesoid'],
            "codigounicovalidacion": data[0]['codigounicovalidacion'],
            "fecharadicacion": data[0]['fecharadicacion'],
            "rutaarchivos": data[0]['rutaarchivos'],
            "tipo_factura": data[0]['tipo_factura'],
            "notificaciones": []
        }
        
        for row in data:
            if row['validacion_id']:
                factura_data["notificaciones"].append({
                    "id": row['validacion_id'],
                    "clase": row['clase'],
                    "codigo": row['codigo'],
                    "descripcion": row['descripcion'],
                    "observaciones": row['observaciones'],
                    "path_fuente": row['path_fuente'],
                    "fuente": row['fuente']
                })
        
        return {
            "success": True,
            "numfactura": request.num_factura,
            "total_notificaciones": len(factura_data["notificaciones"]),
            "factura": factura_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando notificaciones: {str(e)}")
    finally:
        if db and getattr(db, "conn", None):
            db.close()


# =============================================================================
# ENDPOINTS DE ENVIO EVENTO
# =============================================================================

@app.post("/ministerio/envio/fev-rips", tags=["Envio Ministerio"])
def envio_ministerio_fev_rips(request: EnvioMinisterioFevRipsRequest = Body(...)):
    """
    Permite dos modos:
    1) Enviar solo num_factura/numero_factura -> arma JSON automatico (RIPS + XML Base64).
    2) Enviar payload -> usa el JSON tal cual, validando estructura minima.
    """
    conn_sql = None
    conn_postgre = None
    try:
        numero_factura = (request.num_factura or request.numero_factura or "").strip()
        payload = request.payload
        payload_provided = request.payload is not None
        payload_origen = "payload_cliente" if payload_provided else "generado_desde_factura"

        if not payload_provided and not numero_factura:
            raise HTTPException(
                status_code=400,
                detail="Debe enviar num_factura/numero_factura o payload"
            )

        # Si viene payload, validar estructura y usarlo tal cual (sin reconstruir).
        if payload_provided:
            error_validacion = validar_estructura_fev_rips_payload(payload)
            if error_validacion:
                raise HTTPException(status_code=400, detail=error_validacion)
            num_factura_payload = str(payload.get("rips", {}).get("numFactura", "")).strip()
            if numero_factura and num_factura_payload and numero_factura != num_factura_payload:
                raise HTTPException(
                    status_code=400,
                    detail="num_factura/numero_factura no coincide con payload.rips.numFactura"
                )
            if not numero_factura:
                numero_factura = num_factura_payload
        else:
            # Si no viene payload, construir JSON automaticamente con logica de scheduler/main.
            conn_sql = ut.get_db_connection()
            conn_postgre = PSQL(
                dbname=os.getenv("POSTGRES_DBNAME"),
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                host=os.getenv("POSTGRES_HOST")
            )
            conn_postgre.connect()
            payload = construir_payload_fev_rips_desde_num_factura(numero_factura, conn_sql, conn_postgre)

        sender = get_ministerio_sender_autenticado()
        result = sender.send_paquete(
            payload_json=payload,
            tipo_paquete="FEV_RIPS",
            invoice_number=numero_factura or None
        )

        if not result.get("success") and result.get("status_code") is None and "invalido" in str(result.get("message", "")).lower():
            raise HTTPException(status_code=400, detail=result.get("message"))

        # Compatibilidad: RVG18 se maneja como exito operativo.
        if ut.tiene_error_rvg18(result):
            result["success"] = True

        # Persistencia de resultados cuando tenemos numero de factura.
        data_response = result.get("raw_response", {}).get("data", result.get("raw_response"))
        if numero_factura:
            if conn_sql is None:
                conn_sql = ut.get_db_connection()

            sender.update_invoice_status(conn_sql, numero_factura, result, tipo_cargue="INICIAL")
            codigo_retorno = "APROBADO" if result.get("success", False) else "RECHAZADO"
            conn_sql.execute_query(
                """
                UPDATE dbo.rips_af
                SET codigo_retorno = ?, fecha_retorno = ?
                WHERE [numFactura] = ?
                """,
                (codigo_retorno, datetime.now(), numero_factura)
            )
            sender.save_json_soporte_to_db(conn_sql, result, numero_factura, tipo_factura="EVENTO")
            sender.save_facturas_json(
                conn_sql,
                numero_factura,
                payload,
                data_response,
                payload.get("rips", {}),
                "EVENTO"
            )

        return {
            "success": result.get("success", False),
            "tipo_paquete": "FEV_RIPS",
            "numero_factura": numero_factura or None,
            "payload_origen": payload_origen,
            "ministerio_response": data_response,
            "resultado_procesado": {
                "state": result.get("state"),
                "validation_code": result.get("validation_code"),
                "errors": result.get("errors", []),
                "notifications": result.get("notifications", [])
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error enviando FEV_RIPS: {str(e)}')
    finally:
        if conn_sql and getattr(conn_sql, "conn", None):
            conn_sql.close()
        if conn_postgre and getattr(conn_postgre, "conn", None):
            conn_postgre.close()

# =============================================================================
# ENDPOINTS DE ENVIO CAPITA
# =============================================================================

@app.post("/envio/capita-periodo", tags=["Envio CAPITA"])
def envio_capita_periodo(request: EnvioCapitaRequest = Body(...)):
    """
    Enva CAPITA_PERIODO con JSON base completo:
    - Incluye RIPS (como cargue final)
    - Incluye xmlFevFile en Base64 (como cargue inicial)
    """
    conn = None
    conn_postgre = None
    try:
        factura_global_param = request.factura_global

        # Inicializar conexiones
        con_sql_server = SQLServerConnection(
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            server=os.getenv("DB_SERVER")
        )
        conn_postgre = PSQL(
            dbname=os.getenv("POSTGRES_DBNAME"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST")
        )

        # Inicializar el sender
        sender = RipsSender(base_url=os.getenv("MINISTERIO_API_URL"), timeout=300, verify_ssl=False)
        auth_result = sender.authenticate(
            os.getenv("MINISTERIO_TIPO_DOC"),
            os.getenv("MINISTERIO_NUM_DOC"),
            os.getenv("MINISTERIO_CLAVE"),
            os.getenv("MINISTERIO_NIT")
        )

        if not auth_result['success']:
            raise HTTPException(status_code=500, detail='Error en autenticacion con el ministerio')

        conn = con_sql_server
        conn.connect()

        # Obtener facturas relacionadas a la global (misma logica de envio final)
        query = """
            SELECT [numFactura], id_factura, factura_global
            FROM dbo.rips_af
            WHERE tipo_factura = 'C'
              AND estado_registro = 'A'
              AND factura_global = ?;
        """
        facturas = conn.execute_query(query, (factura_global_param,))
        df_facturas = pd.DataFrame(facturas)

        if len(df_facturas) == 0:
            raise HTTPException(
                status_code=404,
                detail=f'No se encontraron facturas para factura_global: {factura_global_param}'
            )

        factura_global = facturas[0]['factura_global']

        # Construir JSON base (RIPS + XML)
        json_factura_capita = EstructuraJsonRips.get_base_json()
        json_factura_capita["rips"]["numFactura"] = factura_global
        json_factura_capita["rips"]["usuarios"] = []

        # ---- Cargar RIPS (como FINAL) ----
        primera_factura = df_facturas.iloc[0]['numFactura']
        datos_af = queries.RipsQueries.get_datos_af(conn, primera_factura)

        if datos_af:
            af = datos_af[0]
            json_factura_capita["rips"]["numDocumentoIdObligado"] = af.get("numDocumentoIdObligado", "")
            json_factura_capita["rips"]["tipoNota"] = af.get("tipoNota")
            json_factura_capita["rips"]["numNota"] = af.get("numNota")

            usuarios_agrupados = {}
            consecutivo_usuario = 1

            for _, row in df_facturas.iterrows():
                id_factura = row['id_factura']
                datos_us = queries.RipsQueries.get_datos_us(conn, id_factura)
                if not datos_us:
                    continue

                usuario_data = datos_us[0].copy()
                num_documento = usuario_data["numDocumentoIdentificacion"]

                if num_documento not in usuarios_agrupados:
                    usuario_data["consecutivo"] = consecutivo_usuario
                    usuario_data["servicios"] = {
                        "consultas": [], "procedimientos": [], "urgencias": [],
                        "hospitalizacion": [], "recienNacidos": [], "medicamentos": [], "otrosServicios": []
                    }
                    usuario_data["_contadores"] = {
                        "consultas": 0, "procedimientos": 0, "urgencias": 0,
                        "hospitalizacion": 0, "recienNacidos": 0, "medicamentos": 0, "otrosServicios": 0
                    }
                    usuarios_agrupados[num_documento] = usuario_data
                    consecutivo_usuario += 1

                servicios_raw = {
                    "consultas": queries.RipsQueries.get_datos_ac(conn, id_factura) or [],
                    "procedimientos": queries.RipsQueries.get_datos_ap(conn, id_factura) or [],
                    "urgencias": queries.RipsQueries.get_datos_au(conn, id_factura) or [],
                    "hospitalizacion": queries.RipsQueries.get_datos_ah(conn, id_factura) or [],
                    "recienNacidos": queries.RipsQueries.get_datos_rn(conn, id_factura) or [],
                    "medicamentos": queries.RipsQueries.get_datos_am(conn, id_factura) or [],
                    "otrosServicios": queries.RipsQueries.get_datos_at(conn, id_factura) or []
                }

                for tipo_servicio, datos in servicios_raw.items():
                    for item in datos:
                        usuarios_agrupados[num_documento]["_contadores"][tipo_servicio] += 1
                        item_actualizado = item.copy()
                        item_actualizado["consecutivo"] = usuarios_agrupados[num_documento]["_contadores"][tipo_servicio]
                        usuarios_agrupados[num_documento]["servicios"][tipo_servicio].append(item_actualizado)

            for usuario in usuarios_agrupados.values():
                usuario_final = usuario.copy()
                del usuario_final["_contadores"]
                usuario_final["servicios"] = {k: v for k, v in usuario_final["servicios"].items() if v}
                json_factura_capita["rips"]["usuarios"].append(usuario_final)

        # ---- Cargar XML (como INICIAL) ----
        conn_postgre.connect()
        datos_xml = queries.RipsQueries.get_datos_attached(conn_postgre, factura_global)
        xml_data = datos_xml[0].get('attached_document', "") if datos_xml else ""
        if not xml_data:
            raise HTTPException(status_code=404, detail='No se encontro XML para la factura')

        base64_xml = b64.ToBase64.xml_texto_a_base64(xml_data)
        if not base64_xml:
            raise HTTPException(status_code=500, detail='Error convirtiendo XML a Base64')
        json_factura_capita["xmlFevFile"] = base64_xml

        # ---- Enviar CAPITA_PERIODO ----
        result = sender.send_paquete(
            payload_json=json_factura_capita,
            tipo_paquete='CAPITA_PERIODO',
            invoice_number=factura_global
        )

        # Compatibilidad RVG18
        if ut.tiene_error_rvg18(result):
            print(f"[ATENCION] Factura {factura_global} tiene error RVG18. Se mover a aprobados.")
            result['success'] = True

        # Persistencia: se maneja como resultado equivalente a envio completo
        sender.update_invoice_status(conn, factura_global, result, tipo_cargue='FINAL')
        sender.save_json_soporte_to_db(conn, result, factura_global, tipo_factura='PERIODO')
        raw_response = result.get('raw_response', result)
        data_response = raw_response.get('data', raw_response)
        sender.save_facturas_json(
            conn,
            factura_global,
            json_factura_capita,
            data_response,
            json_factura_capita.get("rips", {}),
            'PERIODO'
        )

        return {
            'success': result.get('success', False),
            'factura_global': factura_global,
            'tipo_cargue': 'PERIODO',
            'total_facturas': len(df_facturas),
            'total_usuarios': len(json_factura_capita['rips']['usuarios']),
            'ministerio_response': data_response
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error enviando CAPITA_PERIODO: {str(e)}')
    finally:
        if conn and getattr(conn, "conn", None):
            try:
                conn.close()
            except Exception:
                pass
        if conn_postgre and getattr(conn_postgre, "conn", None):
            try:
                conn_postgre.close()
            except Exception:
                pass

@app.post("/capita/envio-inicial", tags=["Envio CAPITA"])
def envio_capita_inicial(request: EnvioCapitaRequest = Body(...)):
    """
    Endpoint para enviar SOLO el XML de la factura capita (cargue inicial)
    """
    conn = None
    try:
        factura_global = request.factura_global
        
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
        
        # Inicializar el sender
        sender = RipsSender(base_url=os.getenv("MINISTERIO_API_URL"), timeout=300, verify_ssl=False)
        auth_result = sender.authenticate(
            os.getenv("MINISTERIO_TIPO_DOC"), 
            os.getenv("MINISTERIO_NUM_DOC"), 
            os.getenv("MINISTERIO_CLAVE"), 
            os.getenv("MINISTERIO_NIT")
        )
        
        if not auth_result['success']:
            logger.error(f"[CAPITA INICIAL] Autenticacion fallida para {factura_global}: {auth_result.get('error', 'Sin detalle')} - {auth_result.get('message', '')}")
            raise HTTPException(status_code=500, detail=f"Error en autenticacion con el ministerio: {auth_result.get('error', 'Sin detalle')}")
        
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
            logger.error(f"[CAPITA INICIAL] Error obteniendo XML para {factura_global}: {xml_error}")
            raise HTTPException(status_code=500, detail=f'Error obteniendo XML: {str(xml_error)}')
        finally:
            connPostgre.close()
        
        if not xml_data:
            raise HTTPException(status_code=404, detail='No se encontro XML para la factura')
        
        base64_xml = b64.ToBase64.xml_texto_a_base64(xml_data)
        if not base64_xml:
            raise HTTPException(status_code=500, detail='Error convirtiendo XML a Base64')
        
        json_factura_capita["xmlFevFile"] = base64_xml
        print(f"[OK] XML convertido a Base64 para factura {factura_global}")
        
        # Enviar al ministerio
        print(f"[ENVIO] Enviando XML inicial para factura {factura_global}...")
        result = sender.send_invoice(json_factura_capita, tipo_cargue='INICIAL')
        
        # Verificar RVG18
        if ut.tiene_error_rvg18(result):
            print(f"[ATENCION] Factura {factura_global} tiene error RVG18. Se mover a aprobados.")
            result['success'] = True
        
        # Actualizar estado en BD
        conn = conSqlServer
        conn.connect()
        update_success = sender.update_invoice_status(conn, factura_global, result, tipo_cargue='INICIAL')
        
        # Guardar JSON soporte
        json_soporte_success = sender.save_json_soporte_to_db(conn, result, factura_global, tipo_factura='INICIAL')
        
        # Guardar en rips_facturas_json
        raw_response = result.get('raw_response', result)
        data_response = raw_response.get('data', raw_response)
        facturas_json_success = sender.save_facturas_json(
            conn, 
            factura_global, 
            json_factura_capita,
            data_response,
            {"xmlFevFile": json_factura_capita.get("xmlFevFile", "")},
            'INICIAL'
        )
        
        return {
            'success': result.get('success', False),
            'factura_global': factura_global,
            'tipo_cargue': 'INICIAL',
            'ministerio_response': data_response
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[CAPITA INICIAL] Error general en factura {request.factura_global}: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f'Error general: {str(e)}')
    finally:
        if conn and getattr(conn, "conn", None):
            try:
                conn.close()
            except Exception:
                pass

@app.post("/capita/envio-final", tags=["Envio CAPITA"])
def envio_capita_final(request: EnvioCapitaRequest = Body(...)):
    """
    Endpoint para enviar SOLO el JSON RIPS sin XML (cargue final)
    """
    try:
        factura_global_param = request.factura_global
        
        # Inicializar conexiones
        conSqlServer = SQLServerConnection(
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            server=os.getenv("DB_SERVER")
        )
        
        # Inicializar el sender
        sender = RipsSender(base_url=os.getenv("MINISTERIO_API_URL"), timeout=300, verify_ssl=False)
        auth_result = sender.authenticate(
            os.getenv("MINISTERIO_TIPO_DOC"), 
            os.getenv("MINISTERIO_NUM_DOC"), 
            os.getenv("MINISTERIO_CLAVE"), 
            os.getenv("MINISTERIO_NIT")
        )
        
        if not auth_result['success']:
            logger.error(f"[CAPITA FINAL] Autenticacion fallida para {factura_global_param}: {auth_result.get('error', 'Sin detalle')} - {auth_result.get('message', '')}")
            raise HTTPException(status_code=500, detail=f"Error en autenticacion con el ministerio: {auth_result.get('error', 'Sin detalle')}")
        
        conn = conSqlServer
        
        # Obtener facturas de la base de datos
        try:
            conn.connect()
            
            query = """ SELECT [numFactura], id_factura, factura_global
                        FROM dbo.rips_af
                        WHERE tipo_factura = 'C'
                        AND estado_registro = 'A'
                        AND factura_global = ?;
                        """
            facturas = conn.execute_query(query, (factura_global_param,))
            df_facturas = pd.DataFrame(facturas)
            
            if len(df_facturas) == 0:
                conn.close()
                raise HTTPException(
                    status_code=404,
                    detail=f'No se encontraron facturas para factura_global: {factura_global_param}'
                )
            
            factura_global = facturas[0]['factura_global']
            
        except HTTPException:
            raise
        except Exception as e:
            conn.close()
            raise HTTPException(status_code=500, detail=f'Error consultando facturas: {str(e)}')
        
        # Procesar facturacin capita - SOLO JSON (sin XML)
        print(f"[PROCESO] Procesando {len(df_facturas)} facturas de capita para factura global: {factura_global} (FINAL)")
        
        json_factura_capita = EstructuraJsonRips.only_json()
        json_factura_capita["rips"]["numFactura"] = factura_global
        json_factura_capita["rips"]["usuarios"] = []
        
        try:
            # Obtener datos AF de la primera factura
            primera_factura = df_facturas.iloc[0]['numFactura']
            datos_af = queries.RipsQueries.get_datos_af(conn, primera_factura)
            
            if datos_af:
                af = datos_af[0]
                json_factura_capita["rips"]["numDocumentoIdObligado"] = af.get("numDocumentoIdObligado", "")
                json_factura_capita["rips"]["tipoNota"] = af.get("tipoNota")
                json_factura_capita["rips"]["numNota"] = af.get("numNota")
            
                # Agrupar usuarios por documento
                usuarios_agrupados = {}
                consecutivo_usuario = 1
                
                for _, row in df_facturas.iterrows():
                    id_factura = row['id_factura']
                    num_factura = row['numFactura']
                    
                    datos_us = queries.RipsQueries.get_datos_us(conn, id_factura)
                    if not datos_us:
                        continue
                    
                    usuario_data = datos_us[0].copy()
                    num_documento = usuario_data["numDocumentoIdentificacion"]
                    
                    if num_documento not in usuarios_agrupados:
                        usuario_data["consecutivo"] = consecutivo_usuario
                        usuario_data["servicios"] = {
                            "consultas": [], "procedimientos": [], "urgencias": [],
                            "hospitalizacion": [], "recienNacidos": [], "medicamentos": [], "otrosServicios": []
                        }
                        usuario_data["_contadores"] = {
                            "consultas": 0, "procedimientos": 0, "urgencias": 0,
                            "hospitalizacion": 0, "recienNacidos": 0, "medicamentos": 0, "otrosServicios": 0
                        }
                        usuarios_agrupados[num_documento] = usuario_data
                        consecutivo_usuario += 1
                    
                    # Obtener servicios
                    servicios_raw = {
                        "consultas": queries.RipsQueries.get_datos_ac(conn, id_factura) or [],
                        "procedimientos": queries.RipsQueries.get_datos_ap(conn, id_factura) or [],
                        "urgencias": queries.RipsQueries.get_datos_au(conn, id_factura) or [],
                        "hospitalizacion": queries.RipsQueries.get_datos_ah(conn, id_factura) or [],
                        "recienNacidos": queries.RipsQueries.get_datos_rn(conn, id_factura) or [],
                        "medicamentos": queries.RipsQueries.get_datos_am(conn, id_factura) or [],
                        "otrosServicios": queries.RipsQueries.get_datos_at(conn, id_factura) or []
                    }
                    
                    for tipo_servicio, datos in servicios_raw.items():
                        if datos:
                            for item in datos:
                                usuarios_agrupados[num_documento]["_contadores"][tipo_servicio] += 1
                                item_actualizado = item.copy()
                                item_actualizado["consecutivo"] = usuarios_agrupados[num_documento]["_contadores"][tipo_servicio]
                                usuarios_agrupados[num_documento]["servicios"][tipo_servicio].append(item_actualizado)
                
                # Convertir a lista de usuarios
                for num_documento, usuario in usuarios_agrupados.items():
                    usuario_final = usuario.copy()
                    del usuario_final["_contadores"]
                    
                    servicios_filtrados = {k: v for k, v in usuario_final["servicios"].items() if v}
                    usuario_final["servicios"] = servicios_filtrados
                    
                    json_factura_capita["rips"]["usuarios"].append(usuario_final)
                
                print(f"[OK] JSON capita FINAL creado con {len(json_factura_capita['rips']['usuarios'])} usuarios (sin XML)")
            
            # Enviar al ministerio
            print(f"[ENVIO] Enviando factura capita FINAL (solo JSON)...")
            result = sender.send_invoice(json_factura_capita, tipo_cargue='FINAL')
            
            # Verificar RVG18
            if ut.tiene_error_rvg18(result):
                print(f"[ATENCION] Factura {factura_global} tiene error RVG18. Se mover a aprobados.")
                result['success'] = True
            
            # Actualizar estado en BD
            update_success = sender.update_invoice_status(conn, factura_global, result, tipo_cargue='FINAL')
            
            # Guardar JSON soporte
            json_soporte_success = sender.save_json_soporte_to_db(conn, result, factura_global, tipo_factura='FINAL')
            
            # Guardar en rips_facturas_json
            json_para_soporte_eps = json_factura_capita.get("rips", {})
            raw_response = result.get('raw_response', result)
            data_response = raw_response.get('data', raw_response)
            facturas_json_success = sender.save_facturas_json(
                conn, 
                factura_global, 
                json_factura_capita,
                data_response,
                json_para_soporte_eps,
                'FINAL'
            )
            
            return {
                'success': result.get('success', False),
                'factura_global': factura_global,
                'tipo_cargue': 'FINAL',
                'total_facturas': len(df_facturas),
                'total_usuarios': len(json_factura_capita['rips']['usuarios'])
            }
            
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            logger.error(f"[CAPITA FINAL] Error procesando factura {factura_global_param}: {str(e)}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f'Error procesando facturacin: {str(e)}')
        finally:
            conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[CAPITA FINAL] Error general en factura {request.factura_global}: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f'Error general: {str(e)}')

@app.post("/capita/obtener-json", tags=["Envio CAPITA"])
def obtener_json_factura(request: ObtenerJsonRequest = Body(...)):
    """
    Obtiene los JSON almacenados de una factura especfica (envio_ministerio, respuesta_ministerio, soporte_eps)
    """
    try:
        num_factura = request.numFactura
        tipo_factura = request.tipo_factura.upper()
        
        if tipo_factura not in ['INICIAL', 'FINAL']:
            raise HTTPException(status_code=400, detail='tipo_factura debe ser INICIAL o FINAL')
        
        conn = SQLServerConnection(
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            server=os.getenv("DB_SERVER")
        )
        
        try:
            query = """
                SELECT 
                    numFactura,
                    envio_ministerio,
                    respuesta_ministerio,
                    soporte_eps,
                    tipo_factura,
                    fecha_creacion
                FROM dbo.rips_facturas_json
                WHERE numFactura = ? AND tipo_factura = ?
            """
            
            result = conn.execute_query(query, (num_factura, tipo_factura), fetch_one=True)
            
            if not result:
                raise HTTPException(
                    status_code=404,
                    detail=f'No se encontro la factura {num_factura} tipo {tipo_factura}'
                )
            
            envio_ministerio = result['envio_ministerio'] if result['envio_ministerio'] else None
            respuesta_ministerio = result['respuesta_ministerio'] if result['respuesta_ministerio'] else None
            soporte_eps = None
            if tipo_factura == 'FINAL':
                soporte_eps = result['soporte_eps'] if result['soporte_eps'] else None
            
            response_data = {
                'success': True,
                'numFactura': result['numFactura'],
                'tipo_factura': result['tipo_factura'],
                'envio_ministerio': envio_ministerio,
                'respuesta_ministerio': respuesta_ministerio
            }
            
            if tipo_factura == 'FINAL':
                response_data['soporte_eps'] = soporte_eps
            
            return response_data
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Error consultando factura: {str(e)}')
        finally:
            conn.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error general: {str(e)}')

@app.post("/capita/notificaciones", tags=["Envio CAPITA"])
def obtener_notificaciones_capita(request: NotificacionesCapitaRequest = Body(...)):
    """
    Obtiene las notificaciones de validacion de envios RIPS CAPITA.
    """
    try:
        num_factura = request.numFactura
        tipo_factura = request.tipo_factura
        
        conn = SQLServerConnection(
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            server=os.getenv("DB_SERVER")
        )
        
        if not conn.connect():
            raise HTTPException(status_code=500, detail='No se pudo conectar a la base de datos')
        
        query = """
            SELECT 
                v.id,
                v.datos_json_soporte_id,
                v.clase,
                v.codigo,
                v.descripcion,
                v.observaciones,
                v.path_fuente,
                v.fuente,
                d.resultstate,
                d.procesoid,
                d.numfactura,
                d.codigounicovalidacion,
                CONVERT(VARCHAR(50), d.fecharadicacion, 120) AS fecharadicacion,
                d.rutaarchivos,
                d.tipo_factura
            FROM [Hospital].[dbo].[rips_json_soporte_resultado_validacion] v
            LEFT JOIN [Hospital].[dbo].[rips_datos_json_soporte] d
                ON v.datos_json_soporte_id = d.id
            WHERE d.numfactura = ? AND d.tipo_factura = ?
            ORDER BY v.id DESC
        """
        
        resultados = conn.execute_query(query, (num_factura, tipo_factura))
        
        if not resultados:
            return {
                'success': True,
                'message': 'No se encontraron notificaciones',
                'data': {
                    'numfactura': num_factura,
                    'tipo_factura': tipo_factura,
                    'validaciones': []
                },
                'count': 0
            }
        
        info_general = {
            'numfactura': resultados[0].get('numfactura'),
            'procesoid': resultados[0].get('procesoid'),
            'codigounicovalidacion': resultados[0].get('codigounicovalidacion'),
            'fecharadicacion': resultados[0].get('fecharadicacion'),
            'resultstate': resultados[0].get('resultstate'),
            'tipo_factura': resultados[0].get('tipo_factura'),
            'rutaarchivos': resultados[0].get('rutaarchivos'),
            'validaciones': []
        }
        
        # Si es tipo FINAL, obtener el JSON para enriquecer
        envio_ministerio = None
        usuarios_rips = []
        
        if tipo_factura == 'FINAL':
            try:
                query_json = """
                    SELECT envio_ministerio
                    FROM dbo.rips_facturas_json
                    WHERE numFactura = ? AND tipo_factura = 'FINAL'
                """
                
                result_json = conn.execute_query(query_json, (num_factura,), fetch_one=True)
                
                if result_json and result_json['envio_ministerio']:
                    envio_ministerio = json.loads(result_json['envio_ministerio'])
                    usuarios_rips = envio_ministerio.get('rips', {}).get('usuarios', [])
                    
            except Exception as analisis_error:
                print(f"[WARNING] Error obteniendo JSON para anlisis: {analisis_error}")
        
        # Agregar todas las validaciones
        for row in resultados:
            validacion = OrderedDict([
                ('clase', row.get('clase')),
                ('codigo', row.get('codigo')),
                ('descripcion', row.get('descripcion')),
                ('observaciones', row.get('observaciones')),
                ('path_fuente', row.get('path_fuente')),
                ('fuente', row.get('fuente')),
                ('tipoDocumento', None),
                ('NumeroDocumento', None),
                ('FacturasAsociadas', None)
            ])
            
            if tipo_factura == 'FINAL' and usuarios_rips:
                path = validacion.get('path_fuente', '')
                match = re.search(r'usuarios\[(\d+)\]', path)
                
                if match:
                    usuario_index = int(match.group(1))
                    consecutivo_usuario = usuario_index + 1
                    
                    usuario_encontrado = None
                    for usuario in usuarios_rips:
                        if usuario.get('consecutivo') == consecutivo_usuario:
                            usuario_encontrado = usuario
                            break
                    
                    if usuario_encontrado:
                        num_documento = usuario_encontrado.get('numDocumentoIdentificacion')
                        tipo_documento = usuario_encontrado.get('tipoDocumentoIdentificacion')
                        
                        validacion['tipoDocumento'] = tipo_documento
                        validacion['NumeroDocumento'] = num_documento
                        
                        try:
                            query_facturas = """
                                SELECT numFactura
                                FROM dbo.rips_af
                                WHERE factura_global = ?
                                    AND NumDocumentoIdentificacion = ?
                                    AND tipo_factura = 'C'
                                    AND estado_factura = 'A'
                            """
                            
                            facturas_individuales = conn.execute_query(
                                query_facturas, 
                                (num_factura, num_documento)
                            )
                            
                            if facturas_individuales:
                                facturas_str = ', '.join([f['numFactura'] for f in facturas_individuales])
                                validacion['FacturasAsociadas'] = facturas_str
                            else:
                                validacion['FacturasAsociadas'] = ''
                                
                        except Exception as facturas_error:
                            validacion['FacturasAsociadas'] = ''
            
            info_general['validaciones'].append(validacion)
        
        response = {
            'success': True,
            'message': f'Se encontraron {len(resultados)} notificaciones',
            'data': info_general,
            'count': len(resultados)
        }
        
        return JSONResponse(content=response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error obteniendo notificaciones: {str(e)}')
    finally:
        if 'conn' in locals() and conn:
            conn.close()

@app.post("/capita/codigos-cuv", tags=["Envio CAPITA"])
def obtener_codigos_cuv(request: EnvioCapitaRequest = Body(...)):
    """
    Obtiene los cdigos CUV de facturas capita especficas
    """
    try:
        factura_global = request.factura_global
        
        conn = SQLServerConnection(
            database=os.getenv("DB_DATABASE"),
            username=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            server=os.getenv("DB_SERVER")
        )
        conn.connect()
        
        codigos_cuv = queries.RipsQueries.get_codigos_cuv_af(conn, factura_global)
        
        if not codigos_cuv:
            raise HTTPException(
                status_code=404,
                detail=f'No se encontraron cdigos CUV para la factura {factura_global}'
            )
        
        return {
            'success': True,
            'factura_global': factura_global,
            'total_registros': len(codigos_cuv),
            'datos': codigos_cuv
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error consultando cdigos CUV: {str(e)}')
    finally:
        if 'conn' in locals():
            conn.close()


# =============================================================================
# ENDPOINTS DE SCHEDULER DE CAPITAS
# =============================================================================

@app.get("/capita/scheduler/status", tags=["Scheduler CAPITA"])
def get_scheduler_status_endpoint():
    """
    Obtiene el estado actual del scheduler de envio automatico de capitas.
    Muestra si esta activo y cuando sera la proxima ejecucion.
    """
    try:
        status = get_scheduler_status()
        return {
            "success": True,
            "scheduler": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error obteniendo estado del scheduler: {str(e)}')


@app.get("/capita/scheduler/pendientes", tags=["Scheduler CAPITA"])
def get_capitas_pendientes_endpoint():
    """
    Obtiene la lista de facturas globales (capitas) que estan pendientes de envio inicial.
    Estas son las capitas que se enviaran en la proxima ejecucion programada.
    """
    try:
        pendientes = get_capitas_pendientes()
        return {
            "success": True,
            "total_pendientes": len(pendientes),
            "capitas_pendientes": pendientes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error obteniendo capitas pendientes: {str(e)}')


@app.post("/capita/scheduler/ejecutar-ahora", tags=["Scheduler CAPITA"])
def ejecutar_envio_capitas_manual():
    """
    Ejecuta manualmente el envio de todas las capitas iniciales pendientes.
    Util para pruebas o cuando se necesita ejecutar fuera del horario programado.
    
     ADVERTENCIA: Este proceso puede tardar varios minutos dependiendo del numero de capitas pendientes.
    """
    try:
        from capita_scheduler import job_enviar_capitas_iniciales
        
        # Ejecutar en un thread separado para no bloquear la API
        import threading
        thread = threading.Thread(target=job_enviar_capitas_iniciales)
        thread.start()
        
        return {
            "success": True,
            "message": "Proceso de envio de capitas iniciado en segundo plano. Revisa los logs para ver el progreso.",
            "log_file": "logs/capita_scheduler.log"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error ejecutando envio manual: {str(e)}')


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    import os
    import sys
    reload_enabled = os.getenv("API_RELOAD", "false").lower() in {"1", "true", "yes"}
    
    # Cambiar el titulo del proceso en Windows
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("API Unificada - Hospital Sagrado Corazon de Jesus")
    
    # Verificar si existen los certificados SSL
    cert_dir = os.path.join(os.path.dirname(__file__), "certs")
    cert_file = os.path.join(cert_dir, "server.crt")
    key_file = os.path.join(cert_dir, "server.key")
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("=" * 70)
        print(" INICIANDO API UNIFICADA CON HTTPS (SSL/TLS)")
        print("=" * 70)
        print(f"Certificado: {cert_file}")
        print(f"Clave privada: {key_file}")
        print(f"URL: https://{os.getenv("API_HOST", "0.0.0.0")}:{int(os.getenv("API_PORT", "8000"))}")
        print(f"Documentacion: https://{os.getenv('API_HOST', '0.0.0.0')}:{int(os.getenv('API_PORT', '8000'))}/docs")
        print("=" * 70)
        
        uvicorn.run(
            "api:app",
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8000")),
            ssl_certfile=cert_file,
            ssl_keyfile=key_file,
            reload=reload_enabled,
            use_colors=False,
            access_log=False,
            timeout_keep_alive=120
        )
    else:
        print("=" * 70)
        print("  CERTIFICADOS SSL NO ENCONTRADOS")
        print("=" * 70)
        print("Iniciando API Unificada con HTTP (sin cifrar)...")
        print(f"URL: http://{os.getenv("API_HOST", "0.0.0.0")}:{int(os.getenv("API_PORT", "8000"))}")
        print(f"Documentacion: http://{os.getenv('API_HOST', '0.0.0.0')}:{int(os.getenv('API_PORT', '8000'))}/docs")
        print("")
        print("Para habilitar HTTPS, ejecuta:")
        print("  cd certs")
        print("  python convert_cert.py")
        print("=" * 70)
        
        uvicorn.run(
            "api:app",
            host=os.getenv("API_HOST", "0.0.0.0"),
            port=int(os.getenv("API_PORT", "8000")),
            reload=reload_enabled,
            use_colors=False,
            access_log=False,
            timeout_keep_alive=120
        )






