from typing import Any, Dict, Optional
import base64
import os

from fastapi import HTTPException

from sql_server_conn import SQLServerConnection, PostgreSQLConnection as PSQL
from EstructuraJson import EstructuraJsonRips
import RipsQueries as queries
import Utilities as b64
from Utilities import Utilities as ut


def _es_diagnostico_valido(valor: Any) -> bool:
    """Un código de diagnóstico cuenta si es un texto no vacío y no un marcador nulo."""
    if valor is None:
        return False
    texto = str(valor).strip()
    return texto != "" and texto.upper() not in ("NULL", "NONE")


def _deduplicar_grupo(item: Dict[str, Any], clave_principal: str, claves_relacionado: list) -> int:
    """
    Deja en None los `claves_relacionado` cuyo valor sea igual al diagnóstico principal
    del grupo (`clave_principal`) o se repita entre los propios relacionados. Modifica el
    ítem in place y devuelve cuántos códigos se eliminaron.
    """
    if not claves_relacionado:
        return 0

    vistos = set()
    principal = item.get(clave_principal)
    if _es_diagnostico_valido(principal):
        vistos.add(str(principal).strip().upper())

    eliminados = 0
    for clave in claves_relacionado:
        valor = item.get(clave)
        if not _es_diagnostico_valido(valor):
            continue
        normalizado = str(valor).strip().upper()
        if normalizado in vistos:
            item[clave] = None      # diagnóstico duplicado: se elimina
            eliminados += 1
        else:
            vistos.add(normalizado)
    return eliminados


def _deduplicar_diagnosticos_item(item: Dict[str, Any]) -> int:
    """
    Para un ítem de servicio (consulta, procedimiento, medicamento, hospitalización,
    urgencia, etc.) deja en None los códigos de diagnóstico RELACIONADO duplicados, para
    evitar los rechazos del Ministerio:
      - relacionado == principal               -> RVC086
      - relacionado repetido entre relacionados -> RVC087
      - relacionado de egreso == principal de egreso (o repetido) -> RVC088

    Se tratan por separado dos grupos, porque el diagnóstico de INGRESO y el de EGRESO
    son independientes:
      - Ingreso: `codDiagnosticoPrincipal`  + `codDiagnosticoRelacionado` / `...Relacionado1/2/3`
      - Egreso:  `codDiagnosticoPrincipalE` + `codDiagnosticoRelacionadoE1/2/3`

    Modifica el ítem in place. Devuelve cuántos códigos se eliminaron.
    """
    relacionados_egreso = sorted(
        clave for clave in item.keys()
        if clave.startswith("codDiagnosticoRelacionadoE")
    )
    relacionados_ingreso = sorted(
        clave for clave in item.keys()
        if clave.startswith("codDiagnosticoRelacionado")
        and not clave.startswith("codDiagnosticoRelacionadoE")
    )

    eliminados = 0
    eliminados += _deduplicar_grupo(item, "codDiagnosticoPrincipal", relacionados_ingreso)
    eliminados += _deduplicar_grupo(item, "codDiagnosticoPrincipalE", relacionados_egreso)
    return eliminados


def limpiar_diagnosticos_duplicados(payload: Dict[str, Any]) -> int:
    """
    Recorre todos los usuarios y servicios del payload RIPS y elimina los códigos de
    diagnóstico relacionado duplicados (ver `_deduplicar_diagnosticos_item`). Así el
    paquete no falla por diagnósticos repetidos (RVC086 / RVC087). Modifica in place.
    Devuelve el total de códigos eliminados.
    """
    if not isinstance(payload, dict):
        return 0

    rips = payload.get("rips", payload)
    if not isinstance(rips, dict):
        return 0

    usuarios = rips.get("usuarios", [])
    if not isinstance(usuarios, list):
        return 0

    total = 0
    for usuario in usuarios:
        if not isinstance(usuario, dict):
            continue
        servicios = usuario.get("servicios", {})
        if not isinstance(servicios, dict):
            continue
        for lista_items in servicios.values():
            if not isinstance(lista_items, list):
                continue
            for item in lista_items:
                if isinstance(item, dict):
                    total += _deduplicar_diagnosticos_item(item)
    return total


def _usuarios_payload(payload: Dict[str, Any]) -> list:
    """Devuelve la lista de usuarios del payload RIPS de forma segura."""
    if not isinstance(payload, dict):
        return []
    rips = payload.get("rips", payload)
    if not isinstance(rips, dict):
        return []
    usuarios = rips.get("usuarios", [])
    return usuarios if isinstance(usuarios, list) else []


def corregir_tipos_documento_usuario(payload: Dict[str, Any], corregir_tipo_doc: bool = True,
                                     corregir_tipo_usuario: bool = True) -> tuple:
    """
    Corrige por usuario el tipoDocumentoIdentificacion según la edad (RC/TI/CC, AS->edad)
    y, solo si `corregir_tipo_usuario` es True, normaliza el tipoUsuario a valores válidos
    (01-04). El tipo de documento se corrige usando la fecha de atención más temprana del
    usuario como referencia de edad.

    OJO: forzar el tipoUsuario a 04 SOLO es válido para CAPITA. En EVENTO el tipoUsuario
    debe conservar el valor real reportado (p.ej. 05), porque debe coincidir con el plan de
    beneficios informado en el XML; si se fuerza a 04 se genera la inconsistencia RIPS-XML
    y el Ministerio rechaza el paquete sin devolver CUV.
    Devuelve (docs_corregidos, tipos_usuario_corregidos).
    """
    n_doc = n_tu = 0
    for u in _usuarios_payload(payload):
        if not isinstance(u, dict):
            continue
        servicios = u.get("servicios", {}) or {}
        if corregir_tipo_doc and u.get("fechaNacimiento"):
            ref = ut.obtener_primera_fecha_atencion(servicios)
            actual = u.get("tipoDocumentoIdentificacion")
            nuevo = ut.corregir_tipo_documento(actual, u.get("fechaNacimiento"), ref)
            if nuevo != actual:
                u["tipoDocumentoIdentificacion"] = nuevo
                n_doc += 1
        if corregir_tipo_usuario:
            actual_tu = u.get("tipoUsuario")
            nuevo_tu = ut.corregir_tipo_usuario(actual_tu)
            if nuevo_tu != actual_tu:
                u["tipoUsuario"] = nuevo_tu
                n_tu += 1
    return n_doc, n_tu


def ajustar_fechas_capita(payload: Dict[str, Any], fecha_factura=None,
                          periodo_inicio=None, periodo_fin=None) -> int:
    """
    Ajusta las fechas de servicio de TODOS los usuarios al periodo de facturación
    (RVC014) y corrige fechaEgreso<fechaInicioAtencion (RVC039). Devuelve el total ajustado.
    """
    total = 0
    for u in _usuarios_payload(payload):
        if isinstance(u, dict):
            total += ut.ajustar_fechas_al_periodo(u.get("servicios", {}) or {},
                                                  fecha_factura, periodo_inicio, periodo_fin)
    return total


def excluir_usuarios_sin_servicios(payload: Dict[str, Any]) -> list:
    """
    Elimina del payload los usuarios que quedaron sin ningún servicio (el Ministerio
    los rechaza) y renumera el consecutivo de usuario de forma contigua (1..N).
    Devuelve la lista de documentos excluidos.
    """
    if not isinstance(payload, dict):
        return []
    rips = payload.get("rips", payload)
    if not isinstance(rips, dict):
        return []
    usuarios = rips.get("usuarios", [])
    if not isinstance(usuarios, list):
        return []

    conservados, excluidos = [], []
    for u in usuarios:
        if not isinstance(u, dict):
            continue
        servicios = {k: v for k, v in (u.get("servicios") or {}).items() if v}
        if not servicios:
            excluidos.append(u.get("numDocumentoIdentificacion"))
            continue
        u["servicios"] = servicios
        conservados.append(u)

    for idx, u in enumerate(conservados, start=1):
        u["consecutivo"] = idx

    rips["usuarios"] = conservados
    return excluidos


def normalizar_payload_capita(payload: Dict[str, Any], fecha_factura=None, xml_data=None,
                              aplicar_periodo: bool = True,
                              excluir_sin_servicios: bool = True,
                              corregir_tipo_usuario: bool = True) -> Dict[str, Any]:
    """
    Aplica todas las normalizaciones que reducen rechazos del Ministerio sobre el payload
    de capita (modifica in place):
      1. Corrige tipoDocumentoIdentificacion por edad y, si `corregir_tipo_usuario` es True,
         normaliza el tipoUsuario a 01-04.
      2. Elimina diagnósticos relacionados duplicados (RVC086/087/088).
      3. Ajusta fechas fuera de periodo (RVC014) y fechaEgreso<ingreso (RVC039).
      4. Excluye usuarios sin servicios y renumera consecutivos.
    El paso 1 (tipo documento) se puede desactivar con la variable CAPITA_CORREGIR_TIPO_DOC=false.
    La normalización de tipoUsuario solo aplica a CAPITA; EVENTO debe llamar con
    `corregir_tipo_usuario=False` para conservar el tipoUsuario real (debe coincidir con el XML).
    Devuelve un resumen con los conteos de cada corrección.
    """
    resumen: Dict[str, Any] = {}

    corregir_doc = os.getenv("CAPITA_CORREGIR_TIPO_DOC", "true").strip().lower() in ("1", "true", "yes", "si", "sí")
    n_doc, n_tu = corregir_tipos_documento_usuario(payload, corregir_tipo_doc=corregir_doc,
                                                   corregir_tipo_usuario=corregir_tipo_usuario)
    resumen["tipo_doc_corregidos"] = n_doc
    resumen["tipo_usuario_corregidos"] = n_tu

    resumen["diagnosticos_eliminados"] = limpiar_diagnosticos_duplicados(payload)

    if aplicar_periodo and (xml_data or fecha_factura):
        periodo_inicio, periodo_fin = (None, None)
        if xml_data:
            periodo_inicio, periodo_fin = ut.obtener_periodo_facturacion_xml(xml_data)
        resumen["fechas_ajustadas"] = ajustar_fechas_capita(payload, fecha_factura, periodo_inicio, periodo_fin)
    else:
        # Sin periodo disponible: al menos corregir egreso<ingreso (RVC039), que es seguro.
        total = 0
        for u in _usuarios_payload(payload):
            if isinstance(u, dict):
                total += ut.corregir_fechas_ingreso_egreso(u.get("servicios", {}) or {})
        resumen["fechas_ajustadas"] = total

    if excluir_sin_servicios:
        excluidos = excluir_usuarios_sin_servicios(payload)
        resumen["usuarios_excluidos"] = len(excluidos)
    else:
        resumen["usuarios_excluidos"] = 0

    return resumen


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

    # Normalización para reducir rechazos (diagnósticos duplicados, tipo doc, egreso<ingreso).
    # En EVENTO no se mueve por periodo ni se excluyen usuarios (es un único usuario) y, sobre
    # todo, NO se corrige el tipoUsuario: debe conservar el valor real reportado (p.ej. 05) para
    # coincidir con el plan de beneficios del XML. Forzarlo a 04 genera la inconsistencia
    # RIPS-XML y el Ministerio rechaza sin devolver CUV. Esa corrección es exclusiva de CAPITA.
    normalizar_payload_capita(json_factura, aplicar_periodo=False, excluir_sin_servicios=False,
                              corregir_tipo_usuario=False)

    datos_xml = queries.RipsQueries.get_datos_attached(conn_postgre, num_factura)
    xml_data = datos_xml[0].get("attached_document", "") if datos_xml else ""
    if not xml_data:
        raise HTTPException(status_code=404, detail=f"No se encontro XML para factura {num_factura}")

    base64_xml = b64.ToBase64.xml_texto_a_base64(xml_data)
    if not base64_xml:
        raise HTTPException(status_code=500, detail=f"No se pudo convertir XML a Base64 para factura {num_factura}")

    json_factura["xmlFevFile"] = base64_xml
    return json_factura
