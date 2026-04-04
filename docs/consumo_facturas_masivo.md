# Guia de Consumo - Endpoints Facturas Masivo

## Alcance

Este documento cubre solo los endpoints de consulta masiva de facturas:

- `GET /facturas/agrupaciones`
- `GET /facturas/por-fecha`
- `GET /facturas/avanzado`

## Base URL

```text
http://<host>:<puerto>
```

## Reglas generales

- Fechas en formato `YYYY-MM-DD`.
- `fecha_inicio` y `fecha_fin` son obligatorias en consultas masivas.
- `solo_aprobadas_con_cuv` por defecto es `true`.
- Si se quiere ver TODO (no solo aprobadas con CUV), enviar `solo_aprobadas_con_cuv=false`.

---

## 1) Catalogos para filtros (entidades y contratos)

### GET `/facturas/agrupaciones`

Devuelve los valores para poblar filtros en cliente:

- Entidades
- Contratos (`contrato_completo`)
- Tipos de entidad

### Ejemplo curl

```bash
curl -X GET "http://<host>:<puerto>/facturas/agrupaciones"
```

### Respuesta ejemplo

```json
{
  "entidades": {
    "total_grupos": 3,
    "datos": [
      {"Entidad": "NUEVA EPS S.A"},
      {"Entidad": "SANITAS"}
    ]
  },
  "contratos": {
    "total_grupos": 2,
    "datos": [
      {"contrato_completo": "1015001 - NUEVA EPS S.A. CONTRIBUTIVO"},
      {"contrato_completo": "01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO"}
    ]
  },
  "tipos_entidad": {
    "total_grupos": 2,
    "datos": [
      {"Tipo_Entidad": "EPS"}
    ]
  }
}
```

---

## 2) Consulta masiva por rango

### GET `/facturas/por-fecha`

Consulta facturas de tipo EVENTO por rango de fecha.

### Parametros

- `fecha_inicio` (obligatorio)
- `fecha_fin` (obligatorio)
- `limit` (opcional, default `1000`, max `10000`)
- `solo_aprobadas_con_cuv` (opcional, default `true`)

### Ejemplo curl

```bash
curl -G "http://<host>:<puerto>/facturas/por-fecha" \
  --data-urlencode "fecha_inicio=2026-03-15" \
  --data-urlencode "fecha_fin=2026-03-19" \
  --data-urlencode "solo_aprobadas_con_cuv=false" \
  --data-urlencode "limit=500"
```

---

## 3) Consulta masiva avanzada (con filtros)

### GET `/facturas/avanzado`

Consulta facturas EVENTO por rango y filtros adicionales.

### Parametros

- `fecha_inicio` (obligatorio)
- `fecha_fin` (obligatorio)
- `entidad` (opcional)
- `contrato` (opcional)
- `tipo_entidad` (opcional)
- `limit` (opcional)
- `solo_aprobadas_con_cuv` (opcional, default `true`)

### Formato recomendado para `contrato`

Enviar el valor seleccionado desde `/facturas/agrupaciones`:

- Ejemplo: `1015001 - NUEVA EPS S.A. CONTRIBUTIVO`

Compatibilidad:

- Version actual del endpoint: acepta `contrato` como solo codigo (`1015001`) o como texto completo (`1015001 - ...`).
- Si un ambiente remoto aun no tiene esta version, puede requerir coincidencia exacta de `contrato_completo` en catalogos.

### Ejemplo curl (recomendado)

```bash
curl -G "http://<host>:<puerto>/facturas/avanzado" \
  --data-urlencode "fecha_inicio=2026-03-15" \
  --data-urlencode "fecha_fin=2026-03-19" \
  --data-urlencode "entidad=NUEVA EPS" \
  --data-urlencode "contrato=1015001 - NUEVA EPS S.A. CONTRIBUTIVO" \
  --data-urlencode "tipo_entidad=EPS" \
  --data-urlencode "solo_aprobadas_con_cuv=false" \
  --data-urlencode "limit=1000"
```

### Respuesta ejemplo

```json
{
  "fecha_inicio": "2026-03-15",
  "fecha_fin": "2026-03-19",
  "filtros_aplicados": {
    "entidad": "NUEVA EPS",
    "contrato": "1015001 - NUEVA EPS S.A. CONTRIBUTIVO",
    "tipo_entidad": "EPS",
    "limit": 1000,
    "solo_aprobadas_con_cuv": false
  },
  "total_registros": 559,
  "facturas": [
    {
      "numFactura": "HSCQ0000191988",
      "fecha_factura": "2026-03-19",
      "codigo_retorno": "APROBADO",
      "codigo_cuv": "....",
      "codigo_cuv_final": "....",
      "Entidad": "NUEVA EPS S.A",
      "Contrato": "1015001 - NUEVA EPS S.A. CONTRIBUTIVO",
      "Tipo_Entidad": "EPS",
      "tipo_factura": "EVENTO"
    }
  ]
}
```

---

## 4) Flujo recomendado de consumo (cliente/Odoo)

1. Consultar `GET /facturas/agrupaciones`.
2. Mostrar al usuario listas de `Entidad`, `Tipo_Entidad` y `contrato_completo`.
3. Enviar filtros a `GET /facturas/avanzado` usando esos valores.
4. Para depuracion funcional, iniciar con `solo_aprobadas_con_cuv=false`.
5. Cuando el resultado sea correcto, activar `solo_aprobadas_con_cuv=true` para salida final.

---

## 5) Ejemplo Python (requests)

```python
import requests

BASE_URL = "http://<host>:<puerto>"

def obtener_catalogos():
    r = requests.get(f"{BASE_URL}/facturas/agrupaciones", timeout=30, verify=False)
    r.raise_for_status()
    return r.json()

def consultar_facturas_avanzado(
    fecha_inicio,
    fecha_fin,
    contrato=None,
    entidad=None,
    tipo_entidad=None,
    limit=1000,
    solo_aprobadas_con_cuv=False,
):
    params = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "solo_aprobadas_con_cuv": str(solo_aprobadas_con_cuv).lower(),
    }

    if contrato:
        # Recomendado: enviar el contrato completo de /facturas/agrupaciones
        params["contrato"] = contrato.strip()

    if entidad:
        params["entidad"] = entidad.strip()

    if tipo_entidad:
        params["tipo_entidad"] = tipo_entidad.strip()

    if limit and int(limit) > 0:
        params["limit"] = int(limit)

    r = requests.get(f"{BASE_URL}/facturas/avanzado", params=params, timeout=30, verify=False)
    r.raise_for_status()
    data = r.json()
    return data.get("facturas", []), data
```

---

## 6) Diagnostico rapido cuando devuelve 0

- Validar que el rango de fechas tenga registros reales.
- Enviar `solo_aprobadas_con_cuv=false` para descartar filtro de CUV/aprobacion.
- Tomar `contrato` directamente desde `/facturas/agrupaciones` (sin editar manualmente).
- Confirmar que el ambiente apuntado (`host:puerto`) tenga la version de API esperada.
