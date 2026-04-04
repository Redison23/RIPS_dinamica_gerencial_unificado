class EstructuraJsonRips:
    @staticmethod
    def get_base_json():
        return {
            "rips": {
                "numDocumentoIdObligado": "",
                "numFactura": "",
                "tipoNota": None,
                "numNota": None,
                "usuarios": [
                    {
                        "tipoDocumentoIdentificacion": "",
                        "numDocumentoIdentificacion": "",
                        "tipoUsuario": "",
                        "fechaNacimiento": "",
                        "codSexo": "",
                        "codPaisResidencia": "",
                        "codMunicipioResidencia": "",
                        "codZonaTerritorialResidencia": "",
                        "incapacidad": "",
                        "codPaisOrigen": "",
                        "consecutivo": 1,
                        "servicios": {
                            "consultas": [],
                            "procedimientos": [],
                            "urgencias": [],
                            "hospitalizacion": [],
                            "recienNacidos": [],
                            "medicamentos": [],
                            "otrosServicios": []
                        }
                    }
                ]
            },
            "xmlFevFile": ""
        }
    

    @staticmethod
    def only_xml():
        return {
            "xmlFevFile": ""
        }

    @staticmethod
    def only_json():
        return {
            "rips": {
                "numDocumentoIdObligado": "",
                "numFactura": "",
                "tipoNota": None,
                "numNota": None,
                "usuarios": [
                    {
                        "tipoDocumentoIdentificacion": "",
                        "numDocumentoIdentificacion": "",
                        "tipoUsuario": "",
                        "fechaNacimiento": "",
                        "codSexo": "",
                        "codPaisResidencia": "",
                        "codMunicipioResidencia": "",
                        "codZonaTerritorialResidencia": "",
                        "incapacidad": "",
                        "codPaisOrigen": "",
                        "consecutivo": 1,
                        "servicios": {
                            "consultas": [],
                            "procedimientos": [],
                            "urgencias": [],
                            "hospitalizacion": [],
                            "recienNacidos": [],
                            "medicamentos": [],
                            "otrosServicios": []
                        }
                    }
                ]
            }
        }