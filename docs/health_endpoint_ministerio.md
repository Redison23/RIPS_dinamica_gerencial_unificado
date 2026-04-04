# Endpoint Health - BD + Ministerio

Este documento describe el nuevo comportamiento de `GET /health`.

## Objetivo

El endpoint ahora valida:

1. Conexión a base de datos (SQL Server).
2. Disponibilidad de envío al Ministerio mediante login (`authenticate`) al servicio SISPRO.

## Request

```bash
curl -X GET "http://<host>:<puerto>/health"
```

## Respuesta (estructura)

```json
{
  "status": "healthy | degraded | unhealthy",
  "timestamp": "ISO8601",
  "database": "connected | disconnected",
  "ministerio_envio": "available | unavailable",
  "envio_disponible": true,
  "checks": {
    "database": {
      "ok": true,
      "test_query": {
        "test": 1
      },
      "error": null
    },
    "ministerio": {
      "ok": true,
      "url": "https://...",
      "timeout_seconds": 20,
      "message": "Autenticación exitosa",
      "error": null
    }
  }
}
```

## Criterio de estado

- `healthy`: BD OK y Ministerio OK.
- `degraded`: solo uno de los dos checks está OK.
- `unhealthy`: ambos checks fallan.

## Ejemplos

### 1) Healthy

```json
{
  "status": "healthy",
  "timestamp": "2026-03-23T16:10:30.120000",
  "database": "connected",
  "ministerio_envio": "available",
  "envio_disponible": true,
  "checks": {
    "database": {
      "ok": true,
      "test_query": {
        "test": 1
      },
      "error": null
    },
    "ministerio": {
      "ok": true,
      "url": "https://sispro-url",
      "timeout_seconds": 20,
      "message": "Autenticación exitosa",
      "error": null
    }
  }
}
```

### 2) Degraded (BD OK, Ministerio no disponible)

```json
{
  "status": "degraded",
  "timestamp": "2026-03-23T16:11:05.200000",
  "database": "connected",
  "ministerio_envio": "unavailable",
  "envio_disponible": false,
  "checks": {
    "database": {
      "ok": true,
      "test_query": {
        "test": 1
      },
      "error": null
    },
    "ministerio": {
      "ok": false,
      "url": "https://sispro-url",
      "timeout_seconds": 20,
      "message": "HTTP 401",
      "error": "Credenciales inválidas"
    }
  }
}
```

### 3) Unhealthy (BD y Ministerio fallando)

```json
{
  "status": "unhealthy",
  "timestamp": "2026-03-23T16:11:40.880000",
  "database": "disconnected",
  "ministerio_envio": "unavailable",
  "envio_disponible": false,
  "checks": {
    "database": {
      "ok": false,
      "test_query": null,
      "error": "Login timeout expired"
    },
    "ministerio": {
      "ok": false,
      "url": "https://sispro-url",
      "timeout_seconds": 20,
      "message": null,
      "error": "Faltan variables de entorno para Ministerio: MINISTERIO_CLAVE"
    }
  }
}
```

## Variables de entorno usadas por check Ministerio

- `MINISTERIO_API_URL`
- `MINISTERIO_TIPO_DOC`
- `MINISTERIO_NUM_DOC`
- `MINISTERIO_CLAVE`
- `MINISTERIO_NIT`
- `MINISTERIO_HEALTH_TIMEOUT` (opcional, default `20` segundos)

Si falta alguna de las obligatorias, `ministerio_envio` será `unavailable`.
