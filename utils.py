"""
Utilidades compartidas para manejo de contraseñas
"""
import hmac
import hashlib
import secrets
from bcrypt import hashpw, gensalt, checkpw
from flask import current_app


def hash_password(password):
    """
    Hash de contraseña completamente aleatorio y único:
    1. Genera una sal aleatoria única de 32 bytes
    2. HMAC con pepper + sal
    3. Bcrypt
    4. Almacena: sal_aleatoria + hash (todo en hex)
    Resultado: Cada hash comienza diferente
    """
    # Obtener pepper desde configuración
    try:
        pepper = current_app.config.get('PEPPER_SECRET', '')
    except RuntimeError:
        from config import Config
        pepper = Config.PEPPER_SECRET
    
    # Generar sal aleatoria única de 32 bytes
    random_salt = secrets.token_bytes(32)
    
    # HMAC con pepper + sal aleatoria
    hmac_hash = hmac.new(
        (pepper + random_salt.hex()).encode('utf-8'),
        password.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # Bcrypt sobre el HMAC
    bcrypt_hash = hashpw(hmac_hash, gensalt(rounds=12))
    
    # Combinar: sal_aleatoria + bcrypt_hash, todo en hexadecimal
    # La sal aleatoria va primero (64 caracteres hex = 32 bytes)
    final_hash = random_salt.hex() + bcrypt_hash.hex()
    
    return final_hash


def verify_password(password, stored_hash):
    """
    Verificar contraseña con el mismo proceso usado en hash_password
    """
    try:
        # Obtener pepper desde configuración
        try:
            pepper = current_app.config.get('PEPPER_SECRET', '')
        except RuntimeError:
            from config import Config
            pepper = Config.PEPPER_SECRET
        
        # Extraer la sal aleatoria (primeros 64 caracteres hex = 32 bytes)
        random_salt_hex = stored_hash[:64]
        bcrypt_hash_hex = stored_hash[64:]
        
        # Convertir de hex a bytes
        random_salt = bytes.fromhex(random_salt_hex)
        bcrypt_hash = bytes.fromhex(bcrypt_hash_hex)
        
        # Recrear el HMAC con la misma sal aleatoria
        hmac_hash = hmac.new(
            (pepper + random_salt_hex).encode('utf-8'),
            password.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # Verificar con bcrypt
        return checkpw(hmac_hash, bcrypt_hash)
        
    except Exception as e:
        print(f"Error verificando contraseña: {str(e)}")
        import traceback
        traceback.print_exc()
        return False