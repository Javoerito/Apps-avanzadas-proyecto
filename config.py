import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Los secretos vienen de variables de entorno (ver .env.example).
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///inventario.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    RESET_TOKEN_MINUTOS = int(os.environ.get("RESET_TOKEN_MINUTOS", 30))
    DIAS_ALERTA_CADUCIDAD = int(os.environ.get("DIAS_ALERTA_CADUCIDAD", 30))
    POR_PAGINA = 10
    ZONA_HORARIA = "America/Guayaquil"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test"
