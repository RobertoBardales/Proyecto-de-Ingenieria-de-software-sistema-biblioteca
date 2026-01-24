import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Configuración general
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tu-clave-secreta-aqui-cambiala'
    
    # Configuración de la base de datos MSSQL - AZURE
    # Para desarrollo local, usa las variables de entorno
    # Para Azure, estas se configurarán en App Service
    
    AZURE_SQL_SERVER = os.environ.get('AZURE_SQL_SERVER') or 'rvsv.database.windows.net'
    AZURE_SQL_DATABASE = os.environ.get('AZURE_SQL_DATABASE') or 'Libreria'
    AZURE_SQL_USER = os.environ.get('AZURE_SQL_USER') or 'morgana'
    AZURE_SQL_PASSWORD = os.environ.get('AZURE_SQL_PASSWORD') or 'MVPAndroid17'
    
    SQLALCHEMY_DATABASE_URI = (
        f'mssql+pyodbc://{AZURE_SQL_USER}:{AZURE_SQL_PASSWORD}@'
        f'{AZURE_SQL_SERVER}:1433/{AZURE_SQL_DATABASE}?'
        f'driver=ODBC+Driver+18+for+SQL+Server&'
        f'Encrypt=yes&'
        f'TrustServerCertificate=no&'
        f'Connection+Timeout=30'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pepper secret para encriptación de contraseñas
    PEPPER_SECRET = os.environ.get('PEPPER_SECRET') or '0ec68042c99439c9cb759e6150bc0306492a4362c4e4fba79a3ec932e41d9bfd'

    # Mail configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or ('Librería Sistema', 'noreply@libreria.com')
    
    # App Configuration
    APP_NAME = 'Sistema Biblioteca'
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL') or 'admin@libreria.com'