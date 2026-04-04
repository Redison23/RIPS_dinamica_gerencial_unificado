"""
Middleware de logging para FastAPI que registra todas las peticiones
"""
import logging
import time
from fastapi import Request
import os
import uuid

# Obtener el logger de la API
logger = logging.getLogger("api_unificada")

async def log_requests_middleware(request: Request, call_next):
    """Middleware para registrar todas las peticiones HTTP"""
    start_time = time.time()
    request_id = str(uuid.uuid4())[:8]  # ID único para cada request
    
    # Verificar si es una solicitud para factura con "NO" (no registrar)
    path_upper = request.url.path.upper()
    skip_logging = "/NO" in path_upper and ("/ESTADO/" in path_upper or "/NOTIFICACIONES-EVENTO" in path_upper)
    
    try:
        response = await call_next(request)
        
        # Calcular tiempo de procesamiento
        process_time = time.time() - start_time
        
        # Registrar solo la respuesta (salida)
        if not skip_logging:
            logger.info(
                f"[{request_id}] {request.method} {request.url.path} "
                f"Status: {response.status_code} "
                f"Time: {process_time:.3f}s"
            )
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            f"[{request_id}] ✗ {request.method} {request.url.path} "
            f"Error: {str(e)} "
            f"Time: {process_time:.3f}s"
        )
        raise
