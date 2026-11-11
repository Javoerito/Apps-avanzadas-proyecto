from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
socketio = SocketIO()

login_manager.login_view = "auth.signin"
login_manager.login_message = "Inicia sesión para continuar."
login_manager.login_message_category = "warning"
