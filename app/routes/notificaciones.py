from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db
from models import Notificaciones, Clientes
from datetime import datetime
from sqlalchemy import desc

bp = Blueprint('notificaciones', __name__, url_prefix='/notificaciones')

@bp.route('/')
@login_required
def listar():
    """Lista todas las notificaciones del usuario actual"""
    try:
        # Obtener filtros
        tipo = request.args.get('tipo', '')
        leido = request.args.get('leido', '')
        
        # Query base - FIXED: Use db.session.query() instead of Model.query
        query = db.session.query(Notificaciones).filter_by(id_cliente=current_user.id_cliente)
        
        # Aplicar filtros
        if tipo:
            query = query.filter_by(tipo=tipo)
        
        if leido:
            leido_bool = leido.lower() == 'true'
            query = query.filter_by(leido=leido_bool)
        
        # Ordenar por fecha (más recientes primero)
        notificaciones = query.order_by(desc(Notificaciones.fecha_envio)).all()
        
        # Contar no leídas
        no_leidas = db.session.query(Notificaciones).filter_by(
            id_cliente=current_user.id_cliente,
            leido=False
        ).count()
        
        return render_template('notificaciones/listar.html',
                             notificaciones=notificaciones,
                             no_leidas=no_leidas,
                             tipo_filtro=tipo,
                             leido_filtro=leido)
    except Exception as e:
        flash(f'Error al cargar notificaciones: {str(e)}', 'danger')
        return redirect(url_for('main.index'))

@bp.route('/crear', methods=['GET', 'POST'])
@login_required
def crear():
    """Crear una nueva notificación (solo para administradores)"""
    # Verificar si el usuario es administrador/empleado

    
    if request.method == 'POST':
        try:
            # Obtener el siguiente ID
            max_id = db.session.query(db.func.max(Notificaciones.id_notificacion)).scalar() or 0
            nuevo_id = max_id + 1
            
            # Obtener datos del formulario
            id_cliente = request.form.get('id_cliente')
            titulo = request.form.get('titulo')
            mensaje = request.form.get('mensaje')
            tipo = request.form.get('tipo')
            
            # Validar campos requeridos
            if not all([id_cliente, titulo, mensaje, tipo]):
                flash('Todos los campos son obligatorios.', 'warning')
                return redirect(url_for('notificaciones.crear'))
            
            # Verificar que el cliente existe
            cliente = db.session.get(Clientes, int(id_cliente))
            if not cliente:
                flash('El cliente seleccionado no existe.', 'danger')
                return redirect(url_for('notificaciones.crear'))
            
            # Crear notificación
            nueva_notificacion = Notificaciones(
                id_notificacion=nuevo_id,
                id_cliente=int(id_cliente),
                titulo=titulo,
                mensaje=mensaje,
                tipo=tipo,
                leido=False,
                fecha_envio=datetime.now()
            )
            
            db.session.add(nueva_notificacion)
            db.session.commit()
            
            flash('Notificación creada exitosamente.', 'success')
            return redirect(url_for('notificaciones.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear notificación: {str(e)}', 'danger')
            return redirect(url_for('notificaciones.crear'))
    
    # GET - Mostrar formulario
    clientes = db.session.query(Clientes).order_by(Clientes.nombres).all()
    return render_template('notificaciones/crear.html', clientes=clientes)

@bp.route('/marcar-leida/<int:id>', methods=['POST'])
@login_required
def marcar_leida(id):
    """Marcar una notificación como leída"""
    try:
        notificacion = db.session.get(Notificaciones, id)
        
        if not notificacion:
            return jsonify({'error': 'Notificación no encontrada'}), 404
        
        # Verificar que la notificación pertenece al usuario
        if notificacion.id_cliente != current_user.id_cliente:
            return jsonify({'error': 'No autorizado'}), 403
        
        notificacion.leido = True
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Notificación marcada como leída'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/marcar-todas-leidas', methods=['POST'])
@login_required
def marcar_todas_leidas():
    """Marcar todas las notificaciones como leídas"""
    try:
        db.session.query(Notificaciones).filter_by(
            id_cliente=current_user.id_cliente,
            leido=False
        ).update({'leido': True})
        
        db.session.commit()
        
        flash('Todas las notificaciones marcadas como leídas.', 'success')
        return redirect(url_for('notificaciones.listar'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
        return redirect(url_for('notificaciones.listar'))

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar una notificación"""
    try:
        notificacion = db.session.get(Notificaciones, id)
        
        if not notificacion:
            flash('Notificación no encontrada.', 'danger')
            return redirect(url_for('notificaciones.listar'))
        
        # Verificar que la notificación pertenece al usuario

        db.session.delete(notificacion)
        db.session.commit()
        
        flash('Notificación eliminada exitosamente.', 'success')
        return redirect(url_for('notificaciones.listar'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar notificación: {str(e)}', 'danger')
        return redirect(url_for('notificaciones.listar'))

@bp.route('/recientes')
@login_required
def recientes():
    """API endpoint para obtener notificaciones recientes"""
    try:
        limit = request.args.get('limit', 5, type=int)
        
        notificaciones = db.session.query(Notificaciones).filter_by(
            id_cliente=current_user.id_cliente
        ).order_by(desc(Notificaciones.fecha_envio)).limit(limit).all()
        
        # Convertir a formato JSON
        notificaciones_json = []
        for notif in notificaciones:
            notificaciones_json.append({
                'id': notif.id_notificacion,
                'titulo': notif.titulo,
                'mensaje': notif.mensaje,
                'tipo': notif.tipo,
                'leida': notif.leido,
                'fecha_creacion': notif.fecha_envio.isoformat() if notif.fecha_envio else None
            })
        
        return jsonify(notificaciones_json)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/contar-no-leidas')
@login_required
def contar_no_leidas():
    """API endpoint para obtener el conteo de notificaciones no leídas"""
    try:
        count = db.session.query(Notificaciones).filter_by(
            id_cliente=current_user.id_cliente,
            leido=False
        ).count()
        
        return jsonify({'count': count})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500