# Guia de consumo actualizada - Descarga Masiva RIPS Evento (Odoo)

Fecha de actualizacion: 2026-03-27
Ambiente validado: `http://45.162.77.222:8001`

## Objetivo
Dejar documentada la forma de consumo que SI retorna facturas en el ambiente actual.

---

## 1) Hallazgo clave (causa del 0)

En este ambiente, el endpoint `/facturas/avanzado` para Nueva EPS esta resolviendo el filtro de contrato con el valor:

- `01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO`

Por eso, consultar con:

- `contrato=1015001`
- `contrato=1015001 - NUEVA EPS S.A. CONTRIBUTIVO`

puede devolver `total_registros=0`, aunque existan facturas en base.

---

## 2) Endpoints usados por Odoo

- `GET /facturas/agrupaciones`
- `GET /facturas/avanzado`

Base URL:

- `http://45.162.77.222:8001`

---

## 3) Flujo correcto para que SI funcione

1. Cargar catalogos con `GET /facturas/agrupaciones`.
2. Tomar `contrato_completo` EXACTO desde `contratos.datos[]`.
3. Enviar ese contrato exacto en `GET /facturas/avanzado`.
4. Para diagnostico inicial, enviar `solo_aprobadas_con_cuv=false`.
5. Leer `facturas` y `total_registros`.

---

## 4) curl probado (funciona)

```bash
curl -G "http://45.162.77.222:8001/facturas/avanzado" --data-urlencode "fecha_inicio=2026-03-15" --data-urlencode "fecha_fin=2026-03-27" --data-urlencode "contrato=01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO" --data-urlencode "limit=500"
```

Opcional para depurar filtros de aprobacion/CUV:

```bash
curl -G "http://45.162.77.222:8001/facturas/avanzado" --data-urlencode "fecha_inicio=2026-03-15" --data-urlencode "fecha_fin=2026-03-27" --data-urlencode "contrato=01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO" --data-urlencode "solo_aprobadas_con_cuv=false" --data-urlencode "limit=500"
```

---

## 5) Correccion recomendada en Odoo (consumo)

### 5.1 Consulta principal

```python
import requests

url_list = "http://45.162.77.222:8001/facturas/avanzado"
params = {
    "fecha_inicio": str(self.start_date),
    "fecha_fin": str(self.end_date),
    "limit": int(self.limit) if self.limit and self.limit > 0 else 500,
}

if self.din_contrato:
    contrato = self.din_contrato.strip()

    # Correccion temporal para este ambiente (2026-03-27):
    # si el usuario selecciona 1015001, forzar contrato que el backend esta usando.
    if contrato == "1015001" or contrato.startswith("1015001 -"):
        contrato = "01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO"

    params["contrato"] = contrato

if self.din_tipo_entidad:
    params["tipo_entidad"] = self.din_tipo_entidad.strip()

if self.din_entidad:
    params["entidad"] = self.din_entidad.strip()

# Recomendado en diagnostico:
# params["solo_aprobadas_con_cuv"] = "false"

response_list = requests.get(url_list, params=params, verify=False, timeout=30)
response_list.raise_for_status()
response_data = response_list.json()

invoices_list = response_data.get("facturas", [])
total_api = response_data.get("total_registros", len(invoices_list))
```

### 5.2 Campo contador correcto

En backend actual el contador es:

- `total_registros`

No usar `total_facturas` para mensaje de resultado.

---

## 6) Error Odoo observado (independiente del endpoint)

Error visto:

- `UnicodeDecodeError: 'ascii' codec can't decode byte ...`

Causa:

- Python 2 + texto con tilde (`Sí`) en concatenacion.

Fix seguro:

```python
error_msg += u"- Solo Aprobadas con CUV: %s\n" % (u"Si" if self.solo_aprobadas_con_cuv else u"No")
```

---

## 7) Checklist rapido

1. Imprimir `response_list.url` y validar query final.
2. Confirmar `status_code` con `raise_for_status()`.
3. Revisar `filtros_aplicados` en la respuesta.
4. Usar `total_registros`.
5. Si sale 0, probar primero con:
   - `solo_aprobadas_con_cuv=false`
   - contrato exacto `01_EVN_890001006 - NUEVA EPS S.A. CONTRIBUTIVO`
