from datetime import datetime
from Utilities import Utilities as ut

class RipsQueries:

    # === AF: Datos principales de la factura ===
    @staticmethod
    def get_datos_af(conn, num_factura: str):
        query = """
            SELECT [numDocumentoIdObligado], [numFactura], [tipoNota], [numNota]
            FROM dbo.rips_af
            WHERE [numFactura] = ?;
        """
        listaConsulta = conn.execute_query(query, (num_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "numDocumentoIdObligado": str(fila["numDocumentoIdObligado"]),
                "numFactura": str(fila["numFactura"]),
                "tipoNota": str(fila["tipoNota"]),
                "numNota": str(fila["numNota"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === US: Usuarios (pacientes) ===
    @staticmethod
    def get_datos_us(conn, id_factura: int):
        query = """
            SELECT [tipoDocumentoIdentificacion], [numDocumentoIdentificacion], [tipoUsuario],
            [fechaNacimiento], [codSexo], [codPaisResidencia], [codMunicipioResidencia],
            [codZonaTerritorialResidencia], [incapacidad], [consecutivo], [codPaisOrigen]
            FROM dbo.rips_us
            WHERE id_factura = ?;
        """

        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "tipoDocumentoIdentificacion": str(fila["tipoDocumentoIdentificacion"]),
                "numDocumentoIdentificacion": str(fila["numDocumentoIdentificacion"]),
                "tipoUsuario": str(fila["tipoUsuario"]),
                "fechaNacimiento": str(fila["fechaNacimiento"]),
                "codSexo": str(fila["codSexo"]),
                "codPaisResidencia": str(fila["codPaisResidencia"]),
                "codMunicipioResidencia": str(fila["codMunicipioResidencia"]),
                "codZonaTerritorialResidencia": str(fila["codZonaTerritorialResidencia"]),
                "incapacidad": fila["incapacidad"],
                "consecutivo": int(fila["consecutivo"]),
                "codPaisOrigen": str(fila["codPaisOrigen"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === AC: Consultas médicas ===
    @staticmethod
    def get_datos_ac(conn, id_factura: int):
        query = """
            SELECT [codPrestador], [fechaInicioAtencion], [numAutorizacion], [codConsulta],
            [modalidadGrupoServicioTecSal], [grupoServicios], [codServicio],
            [finalidadTecnologiaSalud], [causaMotivoAtencion], [codDiagnosticoPrincipal],
            [codDiagnosticoRelacionado1], [codDiagnosticoRelacionado2], [codDiagnosticoRelacionado3],
            [tipoDiagnosticoPrincipal], [tipoDocumentoIdentificacion], [numDocumentoIdentificacion],
            [vrServicio], [conceptoRecaudo], [valorPagoModerador], [numFEVPagoModerador], [consecutivo]
            FROM dbo.rips_ac
            WHERE id_factura = ?;
        """
        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "fechaInicioAtencion": ut.format_datetime(fila["fechaInicioAtencion"]),
                "numAutorizacion": fila["numAutorizacion"],
                "codConsulta": str(fila["codConsulta"]),
                "modalidadGrupoServicioTecSal": str(fila["modalidadGrupoServicioTecSal"]),
                "grupoServicios": str(fila["grupoServicios"]),
                "codServicio": ut.int_or_one(fila["codServicio"]),
                "finalidadTecnologiaSalud": str(fila["finalidadTecnologiaSalud"]),
                "causaMotivoAtencion": str(fila["causaMotivoAtencion"]),
                "codDiagnosticoPrincipal": ut.z000_diag(fila["codDiagnosticoPrincipal"]),
                "codDiagnosticoRelacionado1": fila["codDiagnosticoRelacionado1"],
                "codDiagnosticoRelacionado2": fila["codDiagnosticoRelacionado2"],
                "codDiagnosticoRelacionado3": fila["codDiagnosticoRelacionado3"],
                "tipoDiagnosticoPrincipal": str(fila["tipoDiagnosticoPrincipal"]),
                "tipoDocumentoIdentificacion": ut.type_id(fila["tipoDocumentoIdentificacion"]),
                "numDocumentoIdentificacion": ut.number_id(fila["numDocumentoIdentificacion"]),
                "vrServicio": ut.int_or_one(fila["vrServicio"]),
                "conceptoRecaudo": str(fila["conceptoRecaudo"]),
                #Valor pago moderador puede ser null
                "valorPagoModerador": ut.valorPagoModerador(fila["valorPagoModerador"]),
                "numFEVPagoModerador": fila["numFEVPagoModerador"],
                "consecutivo": int(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === AP: Procedimientos ===
    @staticmethod
    def get_datos_ap(conn, id_factura: int):
        query = """
            SELECT [codPrestador], [fechaInicioAtencion], [idMIPRES], [numAutorizacion], [codProcedimiento],
            [viaIngresoServicioSalud], [modalidadGrupoServicioTecSal], [grupoServicios], [codServicio],
            [finalidadTecnologiaSalud], [tipoDocumentoIdentificacion], [numDocumentoIdentificacion],
            [codDiagnosticoPrincipal], [codDiagnosticoRelacionado], [codComplicacion],
            [vrServicio], [conceptoRecaudo], [valorPagoModerador], [numFEVPagoModerador], [consecutivo]
            FROM dbo.rips_ap
            WHERE id_factura = ?;
        """
        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "fechaInicioAtencion": ut.format_datetime(fila["fechaInicioAtencion"]),
                "idMIPRES": fila["idMIPRES"],
                "numAutorizacion": fila["numAutorizacion"],
                "codProcedimiento": str(fila["codProcedimiento"]),
                "viaIngresoServicioSalud": str(fila["viaIngresoServicioSalud"]),
                "modalidadGrupoServicioTecSal": str(fila["modalidadGrupoServicioTecSal"]),
                "grupoServicios": str(fila["grupoServicios"]),
                "codServicio": ut.int_or_one(fila["codServicio"]),
                "finalidadTecnologiaSalud": str(fila["finalidadTecnologiaSalud"]),
                "tipoDocumentoIdentificacion": ut.type_id(fila["tipoDocumentoIdentificacion"]),
                "numDocumentoIdentificacion": ut.number_id(fila["numDocumentoIdentificacion"]),
                "codDiagnosticoPrincipal": ut.z000_diag(fila["codDiagnosticoPrincipal"]),
                "codDiagnosticoRelacionado": fila["codDiagnosticoRelacionado"],
                "codComplicacion": fila["codComplicacion"],
                "vrServicio": ut.int_or_one(fila["vrServicio"]),
                "conceptoRecaudo": str(fila["conceptoRecaudo"]),
                #Valor pago moderador puede ser null
                "valorPagoModerador": ut.valorPagoModerador(fila["valorPagoModerador"]),
                "numFEVPagoModerador": fila["numFEVPagoModerador"],
                "consecutivo": int(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === AM: Medicamentos ===
    @staticmethod
    def get_datos_am(conn, id_factura: int):
        query = """
            SELECT [codPrestador], [numAutorizacion], [idMIPRES], [fechaDispensAdmon],
            [codDiagnosticoPrincipal], [codDiagnosticoRelacionado], [tipoMedicamento],
            [codTecnologiaSalud], [nomTecnologiaSalud], [concentracionMedicamento], [unidadMedida],
            [formaFarmaceutica], [unidadMinDispensa], [cantidadMedicamento], [diasTratamiento],
            [tipoDocumentoIdentificacion], [numDocumentoIdentificacion],
            [vrUnitMedicamento], [vrServicio], [conceptoRecaudo],
            [valorPagoModerador], [numFEVPagoModerador], [consecutivo]
            FROM dbo.rips_am
            WHERE id_factura = ?;
        """

        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "numAutorizacion": str(fila["numAutorizacion"]),
                "idMIPRES": fila["idMIPRES"],
                "fechaDispensAdmon": ut.format_datetime(fila["fechaDispensAdmon"]),
                "codDiagnosticoPrincipal": ut.z000_diag(fila["codDiagnosticoPrincipal"]),
                "codDiagnosticoRelacionado": fila["codDiagnosticoRelacionado"],
                "tipoMedicamento": str(fila["tipoMedicamento"]),
                "codTecnologiaSalud": ut.str_null(fila["codTecnologiaSalud"]),
                "nomTecnologiaSalud": fila["nomTecnologiaSalud"],
                #Concentracion medicamento puede ser null
                "concentracionMedicamento": ut.int_or_zero(fila["concentracionMedicamento"]),
                #Unidad medida puede ser null
                "unidadMedida": ut.int_or_zero(fila["unidadMedida"]),
                "formaFarmaceutica": fila["formaFarmaceutica"],
                "unidadMinDispensa": ut.int_or_one(fila["unidadMinDispensa"]),
                "cantidadMedicamento": ut.int_or_zero(fila["cantidadMedicamento"]),
                "diasTratamiento": ut.int_or_one(fila["diasTratamiento"]),
                "tipoDocumentoIdentificacion": ut.type_id(fila["tipoDocumentoIdentificacion"]),
                "numDocumentoIdentificacion": ut.number_id(fila["numDocumentoIdentificacion"]),
                "vrUnitMedicamento": ut.int_or_zero(fila["vrUnitMedicamento"]),
                "vrServicio": ut.int_or_zero(fila["vrServicio"]),
                "conceptoRecaudo": str(fila["conceptoRecaudo"]),
                #Valor pago moderador puede ser null
                "valorPagoModerador": ut.valorPagoModerador(fila["valorPagoModerador"]),
                "numFEVPagoModerador": fila["numFEVPagoModerador"],
                "consecutivo": ut.int_or_zero(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === AH: Hospitalización ===
    @staticmethod
    def get_datos_ah(conn, id_factura: int):
        query = """
            SELECT [codPrestador], [viaIngresoServicioSalud], [fechaInicioAtencion], [numAutorizacion],
            [causaMotivoAtencion], [codDiagnosticoPrincipal], [codDiagnosticoPrincipalE],
            [codDiagnosticoRelacionadoE1], [codDiagnosticoRelacionadoE2], [codDiagnosticoRelacionadoE3],
            [codComplicacion], [condicionDestinoUsuarioEgreso], [codDiagnosticoCausaMuerte],
            [fechaEgreso], [consecutivo]
            FROM dbo.rips_ah
            WHERE id_factura = ?;
        """
        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "viaIngresoServicioSalud": str(fila["viaIngresoServicioSalud"]),
                "fechaInicioAtencion": ut.format_datetime(fila["fechaInicioAtencion"]),
                "numAutorizacion": str(fila["numAutorizacion"]),
                "causaMotivoAtencion": str(fila["causaMotivoAtencion"]),
                "codDiagnosticoPrincipal": ut.z000_diag(fila["codDiagnosticoPrincipal"]),
                "codDiagnosticoPrincipalE": ut.str_or_none(fila["codDiagnosticoPrincipalE"]),
                "codDiagnosticoRelacionadoE1": fila["codDiagnosticoRelacionadoE1"],
                "codDiagnosticoRelacionadoE2": fila["codDiagnosticoRelacionadoE2"],
                "codDiagnosticoRelacionadoE3": fila["codDiagnosticoRelacionadoE3"],
                "codComplicacion": fila["codComplicacion"],
                "condicionDestinoUsuarioEgreso": str(fila["condicionDestinoUsuarioEgreso"]),
                "codDiagnosticoCausaMuerte": fila["codDiagnosticoCausaMuerte"],
                "fechaEgreso": ut.format_datetime(fila["fechaEgreso"]),
                "consecutivo": int(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === AU: Atención en urgencias ===
    @staticmethod
    def get_datos_au(conn, id_factura: int):
        query = """
            SELECT [codPrestador], [fechaInicioAtencion], [causaMotivoAtencion],
            [codDiagnosticoPrincipal], [codDiagnosticoPrincipalE], [codDiagnosticoRelacionadoE1],
            [codDiagnosticoRelacionadoE2], [codDiagnosticoRelacionadoE3],
            [condicionDestinoUsuarioEgreso], [codDiagnosticoCausaMuerte], [fechaEgreso], [consecutivo]
            FROM dbo.rips_au
            WHERE id_factura = ?;
        """
        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "fechaInicioAtencion": ut.format_datetime(fila["fechaInicioAtencion"]),
                "causaMotivoAtencion": str(fila["causaMotivoAtencion"]),
                "codDiagnosticoPrincipal": ut.z000_diag(fila["codDiagnosticoPrincipal"]),
                "codDiagnosticoPrincipalE": ut.str_or_none(fila["codDiagnosticoPrincipalE"]),
                "codDiagnosticoRelacionadoE1": fila["codDiagnosticoRelacionadoE1"],
                "codDiagnosticoRelacionadoE2": fila["codDiagnosticoRelacionadoE2"],
                "codDiagnosticoRelacionadoE3": fila["codDiagnosticoRelacionadoE3"],
                "condicionDestinoUsuarioEgreso": ut.int_or_zero_one(fila["condicionDestinoUsuarioEgreso"]),
                "codDiagnosticoCausaMuerte": fila["codDiagnosticoCausaMuerte"],
                "fechaEgreso": ut.format_datetime(fila["fechaEgreso"]),
                "consecutivo": str(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === AT: Otros servicios y tecnologías en salud ===
    @staticmethod
    def get_datos_at(conn, id_factura: int):  
        query = """
            SELECT [codPrestador], [numAutorizacion], [idMIPRES], [fechaSuministroTecnologia], [tipoOS],
            [codTecnologiaSalud], [nomTecnologiaSalud], [cantidadOS],
            [tipoDocumentoIdentificacion], [numDocumentoIdentificacion],
            [vrUnitOS], [vrServicio], [conceptoRecaudo], [valorPagoModerador],
            [numFEVPagoModerador], [consecutivo]
            FROM dbo.rips_at
            WHERE id_factura = ?;
        """
        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "numAutorizacion": fila["numAutorizacion"],
                "idMIPRES": fila["idMIPRES"],
                "fechaSuministroTecnologia": ut.format_datetime(fila["fechaSuministroTecnologia"]),
                "tipoOS": str(fila["tipoOS"]),
                "codTecnologiaSalud": ut.str_null(fila["codTecnologiaSalud"]),
                "nomTecnologiaSalud": fila["nomTecnologiaSalud"],
                "cantidadOS": ut.int_or_one(fila["cantidadOS"]),
                "tipoDocumentoIdentificacion": ut.type_id(fila["tipoDocumentoIdentificacion"]),
                "numDocumentoIdentificacion": ut.number_id(fila["numDocumentoIdentificacion"]),
                "vrUnitOS": ut.int_or_zero(fila["vrUnitOS"]),
                "vrServicio": ut.int_or_zero(fila["vrServicio"]),
                "conceptoRecaudo": str(fila["conceptoRecaudo"]),
                #Valor pago moderador puede ser null
                "valorPagoModerador": ut.valorPagoModerador(fila["valorPagoModerador"]),
                "numFEVPagoModerador": fila["numFEVPagoModerador"],
                "consecutivo": int(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === RN: Recién nacidos ===
    @staticmethod
    def get_datos_rn(conn, id_factura: int):
        query = """
            SELECT [codPrestador], [tipoDocumentoIdentificacion], [numDocumentoIdentificacion],
            [fechaNacimiento], [edadGestacional], [numConsultasCPrenatal], [codSexoBiologico],
            [peso], [codDiagnosticoPrincipal], [condicionDestinoUsuarioEgreso],
            [codDiagnosticoCausaMuerte], [fechaEgreso], [consecutivo]
            FROM dbo.rips_rn
            WHERE id_factura = ?;
        """
        listaConsulta = conn.execute_query(query, (id_factura,))
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "codPrestador": str(fila["codPrestador"]),
                "tipoDocumentoIdentificacion": ut.type_id(fila["tipoDocumentoIdentificacion"]),
                "numDocumentoIdentificacion": ut.number_id(fila["numDocumentoIdentificacion"]),
                "fechaNacimiento": ut.format_datetime(fila["fechaNacimiento"]),
                "edadGestacional": ut.int_or_zero(fila["edadGestacional"]),
                "numConsultasCPrenatal": ut.int_or_one(fila["numConsultasCPrenatal"]),
                "codSexoBiologico": str(fila["codSexoBiologico"]),
                "peso": ut.int_or_one(fila["peso"]),
                "codDiagnosticoPrincipal": ut.z000_diag(fila["codDiagnosticoPrincipal"]),
                "condicionDestinoUsuarioEgreso": str(fila["condicionDestinoUsuarioEgreso"]),
                "codDiagnosticoCausaMuerte": fila["codDiagnosticoCausaMuerte"],
                "fechaEgreso": ut.format_datetime(fila["fechaEgreso"]),
                "consecutivo": int(fila["consecutivo"])
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

    # === XML embebido (DianDocument) - PostgreSQL ===
    @staticmethod
    def get_datos_attached(conn, num_factura: str):
        """
        Obtiene el XML attached_document usando numFactura (dian_code)
        """
        query = """
            SELECT "attached_document"
            FROM public.dian_document
            WHERE dian_code = %s;
        """
        return conn.execute_query(query, (num_factura,))

    # === Obtener códigos CUV de facturas capita ===
    @staticmethod
    def get_codigos_cuv_af(conn, num_factura: str = None):
        """
        Obtiene codigo_cuv y codigo_cuv_global de la tabla rips_af
        Si se proporciona num_factura, filtra por ese número
        Si no, devuelve todos los registros
        """
        if num_factura:
            query = """
                SELECT [numFactura], [codigo_cuv], [codigo_cuv_global]
                FROM [Hospital].[dbo].[rips_af]
                WHERE [numFactura] = ?;
            """
            listaConsulta = conn.execute_query(query, (num_factura,))
        else:
            query = """
                SELECT [numFactura], [codigo_cuv], [codigo_cuv_global]
                FROM [Hospital].[dbo].[rips_af];
            """
            listaConsulta = conn.execute_query(query)
        
        if not listaConsulta:
            return []

        datos_mapeados = []
        for fila in listaConsulta:
            valoresMapeados = {
                "numFactura": str(fila["numFactura"]) if fila.get("numFactura") else "",
                "codigo_cuv": str(fila["codigo_cuv"]) if fila.get("codigo_cuv") else "",
                "codigo_cuv_global": str(fila["codigo_cuv_global"]) if fila.get("codigo_cuv_global") else ""
            }
            datos_mapeados.append(valoresMapeados)
        return datos_mapeados

