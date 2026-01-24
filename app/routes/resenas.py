from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func
from models import Resenas, Libros, Clientes
from app import db
from datetime import datetime
from sqlalchemy.orm import joinedload

bp = Blueprint('resenas', __name__, url_prefix='/resenas')

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID disponible para Resenas"""
    max_id = db.session.execute(
        select(func.max(Resenas.id_resena))
    ).scalar()
    return (max_id or 0) + 1

# ================== RUTAS ==================

@bp.route('/libro/<int:libro_id>/crear', methods=['POST'])
@login_required
def crear(libro_id):
    """Crear nueva reseña para un libro"""
    try:
        # Solo clientes pueden crear reseñas
        if current_user.tipo_usuario != 'cliente':
            return jsonify({'success': False, 'error': 'Solo los clientes pueden dejar reseñas'}), 403
        
        # Validar que el libro existe
        libro = db.session.get(Libros, libro_id)
        if not libro:
            return jsonify({'success': False, 'error': 'Libro no encontrado'}), 404
        
        # Verificar si el usuario ya dejó una reseña para este libro
        resena_existente = db.session.execute(
            select(Resenas).where(
                Resenas.id_libro == libro_id,
                Resenas.id_cliente == current_user.id_cliente
            )
        ).scalars().first()
        
        if resena_existente:
            return jsonify({'success': False, 'error': 'Ya has dejado una reseña para este libro'}), 400
        
        # Obtener datos del formulario
        calificacion = int(request.form.get('calificacion', 0))
        titulo = request.form.get('titulo', '').strip()
        comentario = request.form.get('comentario', '').strip()
        
        # Validaciones
        if calificacion < 1 or calificacion > 5:
            return jsonify({'success': False, 'error': 'La calificación debe ser entre 1 y 5 estrellas'}), 400
        
        if not titulo or len(titulo) < 5:
            return jsonify({'success': False, 'error': 'El título debe tener al menos 5 caracteres'}), 400
        
        if len(titulo) > 200:
            return jsonify({'success': False, 'error': 'El título no puede exceder 200 caracteres'}), 400
        
        if comentario and len(comentario) < 10:
            return jsonify({'success': False, 'error': 'El comentario debe tener al menos 10 caracteres'}), 400
        
        # Crear reseña
        nueva_resena = Resenas(
            id_resena=get_next_id(),
            id_libro=libro_id,
            id_cliente=current_user.id_cliente,
            calificacion=calificacion,
            titulo=titulo,
            comentario=comentario if comentario else None,
            fecha_resena=datetime.now(),
            visible=True  # Por defecto visible, admins pueden ocultar
        )
        
        db.session.add(nueva_resena)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': '¡Gracias por tu reseña!',
            'resena_id': nueva_resena.id_resena
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/listar')
@login_required
def listar():
    """Listar todas las reseñas"""
    resenas = db.session.scalars(
        select(Resenas)
        .options(
            joinedload(Resenas.Libros_),
            joinedload(Resenas.Clientes_)
        )
        .order_by(Resenas.fecha_resena.desc())
    ).unique().all()
    
    return render_template('resenas/listar.html', resenas=resenas)

@bp.route('/editar/<int:id>', methods=['POST'])
@login_required
def editar(id):
    """Editar reseña propia"""
    try:
        resena = db.session.get(Resenas, id)
        
        if not resena:
            return jsonify({'success': False, 'error': 'Reseña no encontrada'}), 404
        
        # Solo el autor puede editar su reseña
        if current_user.tipo_usuario == 'cliente' and resena.id_cliente != current_user.id_cliente:
            return jsonify({'success': False, 'error': 'No tienes permisos para editar esta reseña'}), 403
        
        # Obtener datos
        calificacion = int(request.form.get('calificacion', resena.calificacion))
        titulo = request.form.get('titulo', '').strip()
        comentario = request.form.get('comentario', '').strip()
        
        # Validaciones
        if calificacion < 1 or calificacion > 5:
            return jsonify({'success': False, 'error': 'La calificación debe ser entre 1 y 5 estrellas'}), 400
        
        if not titulo or len(titulo) < 5:
            return jsonify({'success': False, 'error': 'El título debe tener al menos 5 caracteres'}), 400
        
        # Actualizar
        resena.calificacion = calificacion
        resena.titulo = titulo
        resena.comentario = comentario if comentario else None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Reseña actualizada exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar reseña (solo autor o admin)"""
    try:
        resena = db.session.get(Resenas, id)
        
        if not resena:
            return jsonify({'success': False, 'error': 'Reseña no encontrada'}), 404
        
    
        
        db.session.delete(resena)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Reseña eliminada exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/toggle-visibility/<int:id>', methods=['POST'])
@login_required
def toggle_visibility(id):
    """Ocultar/Mostrar reseña (solo admin)"""
    
    try:
        resena = db.session.get(Resenas, id)
        
        if not resena:
            return jsonify({'success': False, 'error': 'Reseña no encontrada'}), 404
        
        resena.visible = not resena.visible
        db.session.commit()
        
        return jsonify({
            'success': True,
            'visible': resena.visible,
            'message': f'Reseña {"mostrada" if resena.visible else "ocultada"} exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500