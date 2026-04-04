# Script para convertir certificado PFX a PEM usando Python
# No requiere OpenSSL instalado

import sys
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
import os

# Configuración
PFX_FILE = "server.pfx"
PASSWORD = b"APIRips2025#Secure"
CERT_FILE = "server.crt"
KEY_FILE = "server.key"

def convert_pfx_to_pem():
    """Convierte archivo PFX a archivos PEM (crt y key)"""
    
    print("🔄 Convirtiendo certificado PFX a formato PEM...")
    
    # Leer archivo PFX
    with open(PFX_FILE, "rb") as f:
        pfx_data = f.read()
    
    # Cargar certificado y clave privada desde PFX
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        pfx_data,
        PASSWORD,
        backend=default_backend()
    )
    
    # Escribir certificado (CRT)
    with open(CERT_FILE, "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))
    print(f"✅ Certificado guardado: {CERT_FILE}")
    
    # Escribir clave privada (KEY)
    with open(KEY_FILE, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    print(f"✅ Clave privada guardada: {KEY_FILE}")
    
    print("✅ Conversión completada exitosamente")

if __name__ == "__main__":
    try:
        convert_pfx_to_pem()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
