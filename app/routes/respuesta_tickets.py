from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from models import RespuestaTicket, Tickets, Clientes, Empleados
from datetime import datetime
from flask_login import login_required, current_user
from sqlalchemy import desc, func

respuesta_tickets = Blueprint('respuesta_tickets', __name__, url_prefix='/respuesta-tickets')


# ==================== CREAR RESPUESTA ====================
@respuesta_tickets.route('/<int:id_ticket>/crear', methods=['POST'])
@login_required
def crear_respuesta(id_ticket):
    """Crear nueva respuesta a un ticket"""
    try:
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            flash('Ticket no encontrado', 'danger')
            return redirect(url_for('tickets.listar_tickets'))
        
        # Verificar permisos
        if hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente != current_user.id_cliente:
                flash('No tienes permiso para responder este ticket', 'danger')
                return redirect(url_for('tickets.listar_tickets'))
        
        mensaje = request.form.get('mensaje', '').strip()
        es_solucion = request.form.get('es_solucion', '0')
        
        # Validaciones
        if not mensaje or len(mensaje) < 3:
            flash('El mensaje debe tener al menos 3 caracteres', 'warning')
            return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
        
        # Obtener el siguiente ID manualmente
        max_id = db.session.query(func.max(RespuestaTicket.id_respuesta)).scalar()
        nuevo_id = (max_id or 0) + 1
        
        # Crear respuesta con ID manual
        respuesta = RespuestaTicket(
            id_respuesta=nuevo_id,
            id_ticket=id_ticket,
            mensaje=mensaje,
            fecha_respuesta=datetime.now(),
            es_solucion=int(es_solucion)
        )
        
        # Asignar quien responde
        if hasattr(current_user, 'id_empleado'):
            respuesta.id_empleado = current_user.id_empleado
        elif hasattr(current_user, 'id_cliente'):
            respuesta.id_cliente = current_user.id_cliente
        
        db.session.add(respuesta)
        
        # Actualizar fecha del ticket
        ticket.fecha_actualizacion = datetime.now()
        
        # Si es solución, cambiar estado
        if int(es_solucion) == 1 and ticket.estado not in ['Cerrado', 'Cancelado']:
            ticket.estado = 'Resuelto'
        
        db.session.commit()
        flash('Respuesta agregada exitosamente', 'success')
        
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar respuesta: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))


# ==================== EDITAR RESPUESTA ====================
@respuesta_tickets.route('/<int:id_respuesta>/editar', methods=['POST'])
@login_required
def editar_respuesta(id_respuesta):
    """Editar una respuesta existente"""
    try:
        respuesta = db.session.get(RespuestaTicket, id_respuesta)
        if not respuesta:
            flash('Respuesta no encontrada', 'danger')
            return redirect(url_for('tickets.listar_tickets'))
        
        # Verificar permisos (solo quien la creó)
        if hasattr(current_user, 'id_empleado'):
            if respuesta.id_empleado != current_user.id_empleado:
                flash('No tienes permiso para editar esta respuesta', 'danger')
                return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))
        elif hasattr(current_user, 'id_cliente'):
            if respuesta.id_cliente != current_user.id_cliente:
                flash('No tienes permiso para editar esta respuesta', 'danger')
                return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))
        
        mensaje = request.form.get('mensaje', '').strip()
        
        if not mensaje or len(mensaje) < 3:
            flash('El mensaje debe tener al menos 3 caracteres', 'warning')
            return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))
        
        respuesta.mensaje = mensaje
        db.session.commit()
        
        flash('Respuesta actualizada exitosamente', 'success')
        return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error al editar respuesta: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))


# ==================== ELIMINAR RESPUESTA ====================
@respuesta_tickets.route('/<int:id_respuesta>/eliminar', methods=['POST'])
@login_required
def eliminar_respuesta(id_respuesta):
    """Eliminar una respuesta"""
    try:
        respuesta = db.session.get(RespuestaTicket, id_respuesta)
        if not respuesta:
            flash('Respuesta no encontrada', 'danger')
            return redirect(url_for('tickets.listar_tickets'))
        
        id_ticket = respuesta.id_ticket
        
        # Verificar permisos (solo quien la creó o admin)
        es_propietario = False
        
        if hasattr(current_user, 'id_empleado'):
            # Empleados pueden eliminar sus propias respuestas
            if respuesta.id_empleado == current_user.id_empleado:
                es_propietario = True
        elif hasattr(current_user, 'id_cliente'):
            # Clientes pueden eliminar sus propias respuestas
            if respuesta.id_cliente == current_user.id_cliente:
                es_propietario = True
        
        if not es_propietario:
            flash('No tienes permiso para eliminar esta respuesta', 'danger')
            return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
        
        db.session.delete(respuesta)
        db.session.commit()
        
        flash('Respuesta eliminada exitosamente', 'success')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
    
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar respuesta: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))


# ==================== MARCAR COMO SOLUCIÓN ====================
@respuesta_tickets.route('/<int:id_respuesta>/marcar-solucion', methods=['POST'])
@login_required
def marcar_solucion(id_respuesta):
    """Marcar una respuesta como solución"""
    try:
        respuesta = db.session.get(RespuestaTicket, id_respuesta)
        if not respuesta:
            return jsonify({'success': False, 'message': 'Respuesta no encontrada'}), 404
        
        ticket = db.session.get(Tickets, respuesta.id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        # Verificar permisos: solo el cliente dueño del ticket o empleados pueden marcar soluciones
        puede_marcar = False
        
        if hasattr(current_user, 'id_empleado'):
            puede_marcar = True
        elif hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente == current_user.id_cliente:
                puede_marcar = True
        
        if not puede_marcar:
            return jsonify({'success': False, 'message': 'No tienes permiso para marcar soluciones'}), 403
        
        # Desmarcar otras soluciones primero (solo una puede ser LA solución)
        otras_soluciones = db.session.query(RespuestaTicket).filter(
            RespuestaTicket.id_ticket == ticket.id_ticket,
            RespuestaTicket.id_respuesta != id_respuesta,
            RespuestaTicket.es_solucion == 1
        ).all()
        
        for otra in otras_soluciones:
            otra.es_solucion = 0
        
        # Marcar esta como solución
        respuesta.es_solucion = 1
        ticket.estado = 'Resuelto'
        ticket.fecha_actualizacion = datetime.now()
        
        db.session.commit()
        
        flash('Respuesta marcada como solución', 'success')
        return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== DESMARCAR SOLUCIÓN ====================
@respuesta_tickets.route('/<int:id_respuesta>/desmarcar-solucion', methods=['POST'])
@login_required
def desmarcar_solucion(id_respuesta):
    """Desmarcar una respuesta como solución"""
    try:
        respuesta = db.session.get(RespuestaTicket, id_respuesta)
        if not respuesta:
            return jsonify({'success': False, 'message': 'Respuesta no encontrada'}), 404
        
        ticket = db.session.get(Tickets, respuesta.id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        # Verificar permisos
        puede_desmarcar = False
        
        if hasattr(current_user, 'id_empleado'):
            puede_desmarcar = True
        elif hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente == current_user.id_cliente:
                puede_desmarcar = True
        
        if not puede_desmarcar:
            return jsonify({'success': False, 'message': 'No tienes permiso'}), 403
        
        # Desmarcar solución
        respuesta.es_solucion = 0
        
        # Verificar si hay otras soluciones
        otras_soluciones = db.session.query(RespuestaTicket).filter(
            RespuestaTicket.id_ticket == ticket.id_ticket,
            RespuestaTicket.es_solucion == 1
        ).count()
        
        # Si no hay más soluciones, cambiar estado a "En Proceso"
        if otras_soluciones == 0 and ticket.estado == 'Resuelto':
            ticket.estado = 'En Proceso'
        
        ticket.fecha_actualizacion = datetime.now()
        db.session.commit()
        
        flash('Solución desmarcada', 'success')
        return redirect(url_for('tickets.ver_ticket', id_ticket=respuesta.id_ticket))
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== API: OBTENER RESPUESTAS ====================
@respuesta_tickets.route('/api/ticket/<int:id_ticket>/respuestas', methods=['GET'])
@login_required
def api_obtener_respuestas(id_ticket):
    """API para obtener todas las respuestas de un ticket"""
    try:
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            return jsonify({'error': 'Ticket no encontrado'}), 404
        
        # Verificar permisos
        if hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente != current_user.id_cliente:
                return jsonify({'error': 'Sin permisos'}), 403
        
        respuestas = db.session.query(RespuestaTicket).filter_by(
            id_ticket=id_ticket
        ).order_by(RespuestaTicket.fecha_respuesta.asc()).all()
        
        return jsonify([{
            'id_respuesta': r.id_respuesta,
            'mensaje': r.mensaje,
            'fecha_respuesta': r.fecha_respuesta.isoformat(),
            'es_solucion': r.es_solucion,
            'es_empleado': r.id_empleado is not None,
            'es_cliente': r.id_cliente is not None
        } for r in respuestas])
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500