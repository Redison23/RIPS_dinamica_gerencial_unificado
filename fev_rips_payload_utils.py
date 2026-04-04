from typing import Any, Dict, Optional
import base64

from fastapi import HTTPException

from sql_server_conn import SQLServerConnection, PostgreSQLConnection as PSQL
from EstructuraJson import EstructuraJsonRips
import RipsQueries as queries
import Utilities as b64


def validar_estructura_fev_rips_payload(payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(payload, dict):
        return "payload debe ser un objeto JSON"

    rips = payload.get("rips")
    if not isinstance(rips, dict):
        return "payload.rips es obligatorio y debe ser un objeto"

    required_rips_keys = [
        "numDocumentoIdObligado", "numFactura", "tipoNota", "numNota", "usuarios"
    ]
    missing_rips_keys = [key for key in required_rips_keys if key not in rips]
    if missing_rips_keys:
        return f"Faltan campos en payload.rips: {', '.join(missing_rips_keys)}"

    if not str(rips.get("numFactura", "")).strip():
        return "payload.rips.numFactura es obligatorio"

    usuarios = rips.get("usuarios")
    if not isinstance(usuarios, list) or len(usuarios) == 0:
        return "payload.rips.usuarios debe ser una lista con al menos un usuario"

    required_usuario_keys = [
        "tipoDocumentoIdentificacion", "numDocumentoIdentificacion", "tipoUsuario",
        "fechaNacimiento", "codSexo", "codPaisResidencia", "codMunicipioResidencia",
        "codZonaTerritorialResidencia", "incapacidad", "codPaisOrigen", "consecutivo", "servicios"
    ]

    for index, usuario in enumerate(usuarios):
        if not isinstance(usuario, dict):
            return f"payload.rips.usuarios[{index}] debe ser un objeto"
        missing_usuario_keys = [key for key in required_usuario_keys if key not in usuario]
        if missing_usuario_keys:
            return f"Faltan campos en payload.rips.usuarios[{index}]: {', '.join(missing_usuario_keys)}"
        if not isinstance(usuario.get("servicios"), dict):
            return f"payload.rips.usuarios[{index}].servicios debe ser un objeto"

    xml_base64 = payload.get("xmlFevFile")
    if not isinstance(xml_base64, str) or not xml_base64.strip():
        return "payload.xmlFevFile es obligatorio y debe ser base64 no vacio"
    try:
        # Remover espacios y saltos de linea para validar base64 real
        xml_base64_limpio = "".join(xml_base64.split())
        base64.b64decode(xml_base64_limpio, validate=True)
    except Exception:
        return "payload.xmlFevFile no tiene formato base64 valido"

    return None


def construir_payload_fev_rips_desde_num_factura(
    num_factura: str,
    conn_sql: SQLServerConnection,
    conn_postgre: PSQL
) -> Dict[str, Any]:
    query_factura_activa = """
        SELECT TOP 1 [numFactura], [id_factura]
        FROM dbo.rips_af
        WHERE [numFactura] = ?
          AND [tipo_factura] = 'E'
          AND [estado_registro] = 'A'
        ORDER BY [id_factura] DESC
    """
    query_factura_evento = """
        SELECT TOP 1 [numFactura], [id_factura]
        FROM dbo.rips_af
        WHERE [numFactura] = ?
          AND [tipo_factura] = 'E'
        ORDER BY [id_factura] DESC
    """
    facturas = conn_sql.execute_query(query_factura_activa, (num_factura,))
    if not facturas:
        facturas = conn_sql.execute_query(query_factura_evento, (num_factura,))
    if not facturas:
        raise HTTPException(status_code=404, detail=f"No se encontro la factura EVENTO {num_factura} en rips_af")

    id_factura = facturas[0]["id_factura"]

    json_factura = EstructuraJsonRips.get_base_json()
    json_factura["rips"]["numFactura"] = num_factura

    datos_af = queries.RipsQueries.get_datos_af(conn_sql, num_factura)
    if datos_af:
        af = datos_af[0]
        json_factura["rips"]["numDocumentoIdObligado"] = af.get("numDocumentoIdObligado", "")
        json_factura["rips"]["tipoNota"] = af.get("tipoNota")
        json_factura["rips"]["numNota"] = af.get("numNota")

    datos_us = queries.RipsQueries.get_datos_us(conn_sql, id_factura)
    if not datos_us:
        raise HTTPException(status_code=404, detail=f"Sin datos de usuario para factura {num_factura}")

    usuario = datos_us[0]
    json_factura["rips"]["usuarios"][0].update(usuario)
    if not usuario.get("consecutivo"):
        json_factura["rips"]["usuarios"][0]["consecutivo"] = 1

    contadores = {
        "consultas": 0, "procedimientos": 0, "urgencias": 0,
        "hospitalizacion": 0, "recienNacidos": 0, "medicamentos": 0, "otrosServicios": 0
    }

    servicios_raw = {
        "consultas": queries.RipsQueries.get_datos_ac(conn_sql, id_factura) or [],
        "procedimientos": queries.RipsQueries.get_datos_ap(conn_sql, id_factura) or [],
        "urgencias": queries.RipsQueries.get_datos_au(conn_sql, id_factura) or [],
        "hospitalizacion": queries.RipsQueries.get_datos_ah(conn_sql, id_factura) or [],
        "recienNacidos": queries.RipsQueries.get_datos_rn(conn_sql, id_factura) or [],
        "medicamentos": queries.RipsQueries.get_datos_am(conn_sql, id_factura) or [],
        "otrosServicios": queries.RipsQueries.get_datos_at(conn_sql, id_factura) or []
    }

    servicios = {}
    for tipo_servicio, datos in servicios_raw.items():
        if datos:
            servicios[tipo_servicio] = []
            for item in datos:
                contadores[tipo_servicio] += 1
                item_actualizado = item.copy()
                item_actualizado["consecutivo"] = contadores[tipo_servicio]
                servicios[tipo_servicio].append(item_actualizado)

    json_factura["rips"]["usuarios"][0]["servicios"] = {k: v for k, v in servicios.items() if v}

    datos_xml = queries.RipsQueries.get_datos_attached(conn_postgre, num_factura)
    xml_data = datos_xml[0].get("attached_document", "") if datos_xml else ""
    if not xml_data:
        raise HTTPException(status_code=404, detail=f"No se encontro XML para factura {num_factura}")

    base64_xml = b64.ToBase64.xml_texto_a_base64(xml_data)
    if not base64_xml:
        raise HTTPException(status_code=500, detail=f"No se pudo convertir XML a Base64 para factura {num_factura}")

    json_factura["xmlFevFile"] = base64_xml
    return json_factura
