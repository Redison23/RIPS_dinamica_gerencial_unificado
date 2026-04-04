import base64

class ToBase64:
    @staticmethod
    def xml_texto_a_base64(xml_texto):
        try:
            # Asegurarse de que xml_texto esté en bytes
            if isinstance(xml_texto, str):
                xml_texto = xml_texto.encode('utf-8')

            contenido_base64 = base64.b64encode(xml_texto).decode('utf-8')
            return contenido_base64
        except Exception as e:
            print(f"Error al convertir el texto XML a base64: {e}")
            return None
