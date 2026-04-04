# Guia de consumo cliente - ejemplos de uso y respuestas

## Base URL

```text
http://<host>:<puerto>
```

Usa siempre header:

```http
Content-Type: application/json
```

En errores, la API responde asi:

```json
{
  "detail": "mensaje de error"
}
```

---

## 1) Health

### GET `/health`

Request:

```bash
curl -X GET "http://<host>:<puerto>/health"
```

Respuesta OK (ejemplo):

```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-03-23T14:12:41.551002",
  "test_query": {
    "test": 1
  }
}
```

---

## 2) Estado factura EVENTO

### GET `/rips_af/estado/{num_factura}`

Request:

```bash
curl -X GET "http://<host>:<puerto>/rips_af/estado/HSCQ0000123456"
```

Respuesta OK (ejemplo):

```json
{
  "numFactura": "HSCQ0000123456",
  "estado": "APROBADO",
  "descripcion": "La factura fue aprobada por el ministerio de salud",
  "codigo_retorno": "APROBADO",
  "codigo_cuv": "f95f6e5a-4b00-4bb8-a1b0-6d8f6d8fd2a1"
}
```

Error 400 (prefijo NO):

```json
{
  "detail": "Tipo de factura no valido: NO123. Las facturas que comienzan con 'NO' no son procesadas."
}
```

Nota cliente: para EVENTO, usa `codigo_cuv` (no `codigo_cuv_global`).

---

## 3) Descarga masiva por rango

### GET `/facturas/por-fecha`

Request:

```bash
curl -G "http://<host>:<puerto>/facturas/por-fecha" \
  --data-urlencode "fecha_inicio=2026-03-01" \
  --data-urlencode "fecha_fin=2026-03-23" \
  --data-urlencode "limit=500" \
  --data-urlencode "solo_aprobadas_con_cuv=true"
```

Respuesta OK (ejemplo):

```json
{
  "fecha_inicio": "2026-03-01",
  "fecha_fin": "2026-03-23",
  "solo_aprobadas_con_cuv": true,
  "total_registros": 2,
  "facturas": [
    {
      "numFactura": "HSCQ0000123456",
      "fecha_factura": "2026-03-22T00:00:00",
      "codigo_retorno": "APROBADO",
      "codigo_cuv": "abc123",
      "codigo_cuv_final": "abc123",
      "envio_ministerio": "{...}",
      "respuesta_ministerio": "{...}",
      "soporte_eps": "{...}",
      "tipo_factura": "EVENTO"
    }
  ]
}
```

---

## 4) Filtro avanzado EVENTO

### GET `/facturas/avanzado`

Request:

```bash
curl -G "http://<host>:<puerto>/facturas/avanzado" \
  --data-urlencode "fecha_inicio=2026-03-01" \
  --data-urlencode "fecha_fin=2026-03-23" \
  --data-urlencode "entidad=NUEVA EPS" \
  --data-urlencode "contrato=12345 - CAPITACION 2026" \
  --data-urlencode "tipo_entidad=EPS" \
  --data-urlencode "limit=200" \
  --data-urlencode "solo_aprobadas_con_cuv=true"
```

Respuesta OK (ejemplo):

```json
{
  "fecha_inicio": "2026-03-01",
  "fecha_fin": "2026-03-23",
  "filtros_aplicados": {
    "entidad": "NUEVA EPS",
    "contrato": "12345 - CAPITACION 2026",
    "tipo_entidad": "EPS",
    "limit": 200,
    "solo_aprobadas_con_cuv": true
  },
  "total_registros": 1,
  "facturas": [
    {
      "numFactura": "HSCQ0000123456",
      "fecha_factura": "2026-03-22T00:00:00",
      "codigo_retorno": "APROBADO",
      "codigo_cuv": "abc123",
      "codigo_cuv_final": "abc123",
      "Entidad": "NUEVA EPS",
      "Contrato": "12345 - CAPITACION 2026",
      "Tipo_Entidad": "EPS",
      "tipo_factura": "EVENTO"
    }
  ]
}
```

Nota cliente: el filtro `contrato` debe enviarse en formato `CODIGO - NOMBRE`.

---

## 5) Catalogos para filtros

### GET `/facturas/agrupaciones`

Request:

```bash
curl -X GET "http://<host>:<puerto>/facturas/agrupaciones"
```

Respuesta OK (ejemplo):

```json
{
  "entidades": {
    "total_grupos": 3,
    "datos": [{"Entidad": "NUEVA EPS"}, {"Entidad": "SANITAS"}]
  },
  "contratos": {
    "total_grupos": 2,
    "datos": [{"contrato_completo": "12345 - CAPITACION 2026"}]
  },
  "tipos_entidad": {
    "total_grupos": 2,
    "datos": [{"Tipo_Entidad": "EPS"}]
  }
}
```

---

## 6) Notificaciones EVENTO

### POST `/facturas/notificaciones-evento`

Request:

```bash
curl -X POST "http://<host>:<puerto>/facturas/notificaciones-evento" \
  -H "Content-Type: application/json" \
  -d '{
    "num_factura": "HSCQ0000123456"
  }'
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "numfactura": "HSCQ0000123456",
  "total_notificaciones": 2,
  "factura": {
    "id": 10,
    "numfactura": "HSCQ0000123456",
    "resultstate": true,
    "procesoid": 123456,
    "codigounicovalidacion": "abc123",
    "fecharadicacion": "2026-03-22 14:05:10.000",
    "rutaarchivos": "...",
    "tipo_factura": "EVENTO",
    "notificaciones": [
      {
        "id": 1,
        "clase": "NOTIFICACION",
        "codigo": "RVG01",
        "descripcion": "...",
        "observaciones": "...",
        "path_fuente": "...",
        "fuente": "..."
      }
    ]
  }
}
```

---

## 7) Envio Ministerio (generico)

### POST `/ministerio/envio`

Request:

```bash
curl -X POST "http://<host>:<puerto>/ministerio/envio" \
  -H "Content-Type: application/json" \
  -d '{
    "tipo_paquete": "FEV_RIPS",
    "numero_factura": "HSCQ0000123456",
    "payload": {
      "rips": {
        "numFactura": "HSCQ0000123456"
      },
      "xmlFevFile": "BASE64_XML_AQUI"
    }
  }'
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "tipo_paquete": "FEV_RIPS",
  "numero_factura": "HSCQ0000123456",
  "ministerio_response": {
    "ResultState": true,
    "NumFactura": "HSCQ0000123456",
    "CodigoUnicoValidacion": "abc123"
  },
  "resultado_procesado": {
    "state": "APROBADO",
    "validation_code": "abc123",
    "errors": [],
    "notifications": []
  }
}
```

---

## 8) Envio Ministerio (atajo)

### POST `/ministerio/envio/fev-rips`

Request:

```bash
curl -X POST "http://<host>:<puerto>/ministerio/envio/fev-rips" \
  -H "Content-Type: application/json" \
  -d '{
    "numero_factura": "HSCQ0000123456",
    "payload": {
      "rips": {
        "numFactura": "HSCQ0000123456"
      },
      "xmlFevFile": "BASE64_XML_AQUI"
    }
  }'
```

Respuesta: mismo formato de `/ministerio/envio`.

Atajos disponibles:

- `/ministerio/envio/fev-rips`
- `/ministerio/envio/nc`
- `/ministerio/envio/nc-total`
- `/ministerio/envio/nd`
- `/ministerio/envio/nota-ajuste`
- `/ministerio/envio/nc-acuerdo-voluntades`
- `/ministerio/envio/consultar-cuv`

### POST `/envio/capita-periodo`

Request:

```bash
curl -X POST "http://<host>:<puerto>/envio/capita-periodo" \
  -H "Content-Type: application/json" \
  -d '{
    "factura_global": "HSCQ0000168522"
  }'
```

Comportamiento:
- Construye internamente `get_base_json` (RIPS + `xmlFevFile`).
- Toma RIPS de SQL Server (como envio final).
- Toma XML de PostgreSQL y lo convierte a Base64 (como envio inicial).
- Envia al Ministerio por `CAPITA_PERIODO`.

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "factura_global": "HSCQ0000168522",
  "tipo_cargue": "PERIODO",
  "total_facturas": 12,
  "total_usuarios": 12,
  "ministerio_response": {
    "ResultState": true,
    "NumFactura": "HSCQ0000168522",
    "CodigoUnicoValidacion": "abc123"
  }
}
```

---

## 9) CAPITA inicial

### POST `/capita/envio-inicial`

Request:

```bash
curl -X POST "http://<host>:<puerto>/capita/envio-inicial" \
  -H "Content-Type: application/json" \
  -d '{
    "factura_global": "HSCQ0000168522"
  }'
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "factura_global": "HSCQ0000168522",
  "tipo_cargue": "INICIAL",
  "ministerio_response": {
    "ResultState": true,
    "NumFactura": "HSCQ0000168522",
    "CodigoUnicoValidacion": "abc123"
  }
}
```

---

## 10) CAPITA final

### POST `/capita/envio-final`

Request:

```bash
curl -X POST "http://<host>:<puerto>/capita/envio-final" \
  -H "Content-Type: application/json" \
  -d '{
    "factura_global": "HSCQ0000168522"
  }'
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "factura_global": "HSCQ0000168522",
  "tipo_cargue": "FINAL",
  "total_facturas": 12,
  "total_usuarios": 12
}
```

---

## 11) Consultar JSON guardados CAPITA

### POST `/capita/obtener-json`

Request:

```bash
curl -X POST "http://<host>:<puerto>/capita/obtener-json" \
  -H "Content-Type: application/json" \
  -d '{
    "numFactura": "HSCQ0000168522",
    "tipo_factura": "FINAL"
  }'
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "numFactura": "HSCQ0000168522",
  "tipo_factura": "FINAL",
  "envio_ministerio": "{...}",
  "respuesta_ministerio": "{...}",
  "soporte_eps": "{...}"
}
```

Error 400 (tipo_factura invalido):

```json
{
  "detail": "tipo_factura debe ser INICIAL o FINAL"
}
```

---

## 12) Notificaciones CAPITA

### POST `/capita/notificaciones`

Request:

```bash
curl -X POST "http://<host>:<puerto>/capita/notificaciones" \
  -H "Content-Type: application/json" \
  -d '{
    "numFactura": "HSCQ0000168522",
    "tipo_factura": "FINAL"
  }'
```

Respuesta OK con datos (ejemplo):

```json
{
  "success": true,
  "message": "Se encontraron 3 notificaciones",
  "data": {
    "numfactura": "HSCQ0000168522",
    "procesoid": 123456,
    "codigounicovalidacion": "abc123",
    "fecharadicacion": "2026-03-22 14:05:10",
    "resultstate": true,
    "tipo_factura": "FINAL",
    "rutaarchivos": "...",
    "validaciones": [
      {
        "clase": "NOTIFICACION",
        "codigo": "RVG01",
        "descripcion": "...",
        "observaciones": "...",
        "path_fuente": "rips.usuarios[0]...",
        "fuente": "...",
        "tipoDocumento": "CC",
        "NumeroDocumento": "123456789",
        "FacturasAsociadas": "FAC001,FAC002"
      }
    ]
  },
  "count": 3
}
```

Respuesta OK sin datos (ejemplo):

```json
{
  "success": true,
  "message": "No se encontraron notificaciones",
  "data": {
    "numfactura": "HSCQ0000168522",
    "tipo_factura": "FINAL",
    "validaciones": []
  },
  "count": 0
}
```

---

## 13) Codigos CUV CAPITA

### POST `/capita/codigos-cuv`

Request:

```bash
curl -X POST "http://<host>:<puerto>/capita/codigos-cuv" \
  -H "Content-Type: application/json" \
  -d '{
    "factura_global": "HSCQ0000168522"
  }'
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "factura_global": "HSCQ0000168522",
  "total_registros": 1,
  "datos": [
    {
      "numFactura": "HSCQ0000168522",
      "codigo_cuv": "abc123",
      "codigo_cuv_global": "xyz999"
    }
  ]
}
```

---

## 14) Scheduler CAPITA

### GET `/capita/scheduler/status`

```bash
curl -X GET "http://<host>:<puerto>/capita/scheduler/status"
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "scheduler": {
    "is_running": true,
    "next_run_time": "2026-03-24T00:00:00"
  }
}
```

### GET `/capita/scheduler/pendientes`

```bash
curl -X GET "http://<host>:<puerto>/capita/scheduler/pendientes"
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "total_pendientes": 2,
  "capitas_pendientes": [
    "HSCQ0000168522",
    "HSCQ0000168523"
  ]
}
```

### POST `/capita/scheduler/ejecutar-ahora`

```bash
curl -X POST "http://<host>:<puerto>/capita/scheduler/ejecutar-ahora"
```

Respuesta OK (ejemplo):

```json
{
  "success": true,
  "message": "Proceso de envio de capitas iniciado en segundo plano. Revisa los logs para ver el progreso.",
  "log_file": "logs/capita_scheduler.log"
}
```
