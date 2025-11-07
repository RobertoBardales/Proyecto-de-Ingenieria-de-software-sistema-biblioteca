from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func
from models import MensajesForos, TemasForos
from app import db
from datetime import datetime

bp = Blueprint('mensajes_foros', __name__, url_prefix='/mensajes_foros')

def get_next_id():
    """Obtiene el siguiente ID disponible para MensajesForos"""
    max_id = db.session.execute(
        select(func.max(MensajesForos.id_mensaje))
    ).scalar()
    return (max_id or 0) + 1

@bp.route('/nuevo', methods=['POST'])
@login_required
def nuevo():
    """Crea una nueva respuesta en un tema"""
    try:
        id_tema = int(request.form.get('id_tema'))
        contenido = request.form.get('contenido', '').strip()
        
        # Validar que el tema existe
        tema = db.session.get(TemasForos, id_tema)
        if not tema:
            flash('Tema no encontrado', 'error')
            return redirect(url_for('temas_foros.listar'))
        
        # Validar que el tema está activo
        if not tema.activo:
            flash('Este tema está cerrado y no acepta respuestas', 'error')
            return redirect(url_for('temas_foros.ver', id=id_tema))
        
        # Validar contenido
        if len(contenido) < 5:
            flash('La respuesta debe tener al menos 5 caracteres', 'error')
            return redirect(url_for('temas_foros.ver', id=id_tema))
        
        if len(contenido) > 2000:
            flash('La respuesta no puede exceder 2000 caracteres', 'error')
            return redirect(url_for('temas_foros.ver', id=id_tema))
        
        # Crear mensaje
        nuevo_mensaje = MensajesForos(
            id_mensaje=get_next_id(),
            id_tema=id_tema,
            id_cliente=current_user.id_cliente,
            contenido=contenido,
            fecha_publicacion=datetime.now(),
            visible=True,
            id_mensaje_padre=None
        )
        
        db.session.add(nuevo_mensaje)
        db.session.commit()
        
        flash('✅ Respuesta publicada exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al publicar respuesta: {str(e)}', 'error')
    
    return redirect(url_for('temas_foros.ver', id=id_tema))

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Elimina un mensaje (solo autor o admin) - soft delete"""
    try:
        mensaje = db.session.get(MensajesForos, id)
        
        if not mensaje:
            flash('Mensaje no encontrado', 'error')
            return redirect(url_for('temas_foros.listar'))
        
        # Verificar permisos
        if mensaje.id_cliente != current_user.id_cliente and current_user.tipo_usuario != 'admin':
            flash('No tienes permisos para eliminar este mensaje', 'error')
            return redirect(url_for('temas_foros.ver', id=mensaje.id_tema))
        
        id_tema = mensaje.id_tema
        
        # Soft delete: marcar como no visible
        mensaje.visible = False
        mensaje.fecha_edicion = datetime.now()
        
        db.session.commit()
        
        flash('✅ Mensaje eliminado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar mensaje: {str(e)}', 'error')
    
    return redirect(url_for('temas_foros.ver', id=id_tema))