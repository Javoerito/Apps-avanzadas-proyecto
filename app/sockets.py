"""Chat y notificaciones en tiempo real (Flask-SocketIO, servidor propio dentro del monolito)."""
import re
import threading

from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from .extensions import db, socketio
from .models import Mensaje, SalaChat

MAX_MENSAJE = 500
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
conectados = {}  # sid -> {"user_id", "nombre", "sala"}
_lock = threading.Lock()


def _presencia():
    with _lock:
        unicos = {c["user_id"]: c["nombre"] for c in conectados.values()}
    return sorted(unicos.values(), key=str.lower)


def _sala(sid_sala):
    return f"sala_{sid_sala}"


def _iso(dt):
    return dt.isoformat() + "Z"


def _mensaje_json(m):
    return {"id": m.id, "usuario": m.usuario.nombre, "usuario_id": m.usuario_id, "texto": m.contenido,
            "fecha": _iso(m.creado_en)}


@socketio.on("connect")
def al_conectar():
    # Autenticación en el handshake: se usa la sesión (cookie firmada) de Flask-Login.
    if not current_user.is_authenticated:
        return False
    with _lock:
        conectados[request.sid] = {"user_id": current_user.id, "nombre": current_user.nombre, "sala": None}
    emit("presencia", _presencia(), broadcast=True)


@socketio.on("disconnect")
def al_desconectar(*_):
    with _lock:
        conectados.pop(request.sid, None)
    emit("presencia", _presencia(), broadcast=True)


@socketio.on("unirse")
def unirse(data):
    info = conectados.get(request.sid)
    sala_id = data.get("sala_id") if isinstance(data, dict) else None
    sala = db.session.get(SalaChat, sala_id) if isinstance(sala_id, int) and info else None
    if not sala:
        return emit("error_chat", {"mensaje": "Sala no válida."})
    if info["sala"]:
        leave_room(_sala(info["sala"]))
    join_room(_sala(sala.id))
    info["sala"] = sala.id
    ultimos = (Mensaje.query.filter_by(sala_id=sala.id).order_by(Mensaje.id.desc()).limit(50).all())
    emit("historial", {"sala_id": sala.id, "sala": sala.nombre, "mensajes": [_mensaje_json(m) for m in reversed(ultimos)]})


@socketio.on("mensaje")
def mensaje(data):
    info = conectados.get(request.sid)
    if not info or not isinstance(data, dict):
        return
    texto = data.get("texto")
    if not isinstance(texto, str):
        return emit("error_chat", {"mensaje": "Mensaje inválido."})
    texto = _CONTROL.sub("", texto).strip()
    if not texto or len(texto) > MAX_MENSAJE:
        return emit("error_chat", {"mensaje": f"El mensaje debe tener entre 1 y {MAX_MENSAJE} caracteres."})
    if data.get("sala_id") != info["sala"] or not info["sala"]:
        return emit("error_chat", {"mensaje": "Únete a una sala antes de escribir."})
    m = Mensaje(sala_id=info["sala"], usuario_id=info["user_id"], contenido=texto)
    db.session.add(m)
    db.session.commit()
    emit("mensaje", dict(_mensaje_json(m), sala_id=info["sala"]), to=_sala(info["sala"]))
