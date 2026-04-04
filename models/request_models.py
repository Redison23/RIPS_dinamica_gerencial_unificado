from typing import Any, Dict, Optional

from pydantic import BaseModel


class NotificacionesEventoRequest(BaseModel):
    num_factura: str

    class Config:
        json_schema_extra = {
            "example": {
                "num_factura": "123456"
            }
        }


class EnvioCapitaRequest(BaseModel):
    factura_global: str

    class Config:
        json_schema_extra = {
            "example": {
                "factura_global": "HSCQ0000168522"
            }
        }


class EnvioMinisterioFevRipsRequest(BaseModel):
    num_factura: Optional[str] = None
    numero_factura: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "num_factura": "HSCQ0000000001"
            }
        }


class ObtenerJsonRequest(BaseModel):
    numFactura: str
    tipo_factura: str

    class Config:
        json_schema_extra = {
            "example": {
                "numFactura": "HSCQ0000168522",
                "tipo_factura": "FINAL"
            }
        }


class NotificacionesCapitaRequest(BaseModel):
    numFactura: str
    tipo_factura: str

    class Config:
        json_schema_extra = {
            "example": {
                "numFactura": "HSCQ0000168522",
                "tipo_factura": "FINAL"
            }
        }
