# KIROX-FEVRIPS

Proyecto **unificado** del Hospital Sagrado Corazón de Jesús de Quimbaya. Reemplaza y
consolida los antiguos proyectos `API_Unificada` y `kirox-fevrips - envio` en una sola
base de código y un solo servicio de Windows.

## Qué hace

1. **Consulta RIPS para Odoo** — API REST (FastAPI) en el puerto `8001` que expone el estado
   de facturas, notificaciones, agrupaciones, etc.
2. **Envío CAPITA** — endpoints de envío inicial/final/periodo + scheduler diario (1:05 AM).
3. **Envío automático EVENTO** — *(integrado desde el antiguo kirox)* scheduler que cada
   30 min envía al Ministerio las facturas EVENTO pendientes (sin CUV, últimos 40 días).
   Reemplaza al servicio `RipsSchedulerService`.

## Resiliencia / auto-reinicio

La API corre como servicio de Windows `KiroxFevrips` con tres capas de recuperación:

- **Timeouts de BD** (`sql_server_conn.py`): `connect()` ya no se cuelga si SQL Server tiene
  un blip de red — falla rápido según `DB_LOGIN_TIMEOUT`. Esto resuelve el síntoma de
  "la API se queda pegada y no responde".
- **Auto-relanzamiento** (`api_service.py`): si el proceso `uvicorn` muere, el servicio lo
  vuelve a levantar con backoff.
- **Watchdog interno**: sonda `GET /ping` cada `WATCHDOG_INTERVAL` segundos; si falla
  `WATCHDOG_FAILS` veces seguidas (API colgada pero proceso vivo), mata y relanza `uvicorn`.
- **Windows Recovery**: `sc failure` reinicia el servicio si el proceso entero cae.

## Endpoints nuevos

| Endpoint | Descripción |
|----------|-------------|
| `GET /ping` | Sonda liviana (no toca BD). La usa el watchdog. |
| `GET /evento/scheduler/status` | Estado del scheduler de envío automático EVENTO. |
| `GET /evento/scheduler/pendientes` | Facturas EVENTO pendientes de envío. |
| `POST /evento/scheduler/ejecutar-ahora` | Dispara el envío EVENTO manualmente (en segundo plano). |

(Endpoints de consulta y CAPITA: ver `docs/endpoints_api.md`.)

## Instalación / despliegue

```bat
:: 1) Crear el entorno virtual e instalar dependencias
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

:: 2) Instalar como servicio de Windows (clic derecho -> Ejecutar como administrador)
instalar_servicio.bat
```

El servicio queda en inicio automático, con recovery y watchdog activos.

Para desinstalar: `desinstalar_servicio.bat` (como administrador).

## Configuración (.env)

Además de las credenciales de BD / Ministerio / PostgreSQL, hay variables de resiliencia:

| Variable | Default | Para qué |
|----------|---------|----------|
| `DB_LOGIN_TIMEOUT` | 5 | Timeout de conexión a SQL Server (s). |
| `DB_QUERY_TIMEOUT` | 30 | Timeout de query (s). |
| `PG_CONNECT_TIMEOUT` | 5 | Timeout de conexión a PostgreSQL (s). |
| `DB_LOG_LEVEL` | WARNING | `DEBUG` para ver conexiones; `WARNING` las silencia. |
| `EVENTO_SCHEDULER_INTERVAL_MIN` | 30 | Frecuencia del envío automático EVENTO (min). |
| `WATCHDOG_ENABLED` | true | Activa/desactiva el watchdog. |
| `WATCHDOG_INTERVAL` | 30 | Segundos entre sondas `/ping`. |
| `WATCHDOG_TIMEOUT` | 5 | Timeout de cada sonda (s). |
| `WATCHDOG_FAILS` | 3 | Fallos seguidos antes de reiniciar `uvicorn`. |
| `WATCHDOG_GRACE` | 30 | Gracia tras arrancar/reiniciar (s). |
| `SERVICE_RESTART_BACKOFF` | 3 | Backoff inicial entre reintentos (s). |
| `SERVICE_RESTART_BACKOFF_MAX` | 30 | Backoff máximo (s). |

## Nota sobre el cliente Odoo

El módulo Odoo "Facturas RIPS Evento" consulta esta API con un `read timeout=2` segundos,
muy agresivo. Se recomienda subirlo a ~10 s en el lado de Odoo para tolerar picos
puntuales (ese cambio vive en el código de Odoo, fuera de este repositorio).
