from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app import db
from models import Tickets, RespuestaTicket, Clientes, Empleados
from datetime import datetime
from flask_login import login_required, current_user
from sqlalchemy import desc, func

tickets = Blueprint('tickets', __name__, url_prefix='/tickets')


# ==================== LISTA DE TICKETS ====================
@tickets.route('/')
@login_required
def listar_tickets():
    """Lista todos los tickets (admin ve todos, cliente ve solo los suyos)"""
    try:
        # Parámetros de paginación y filtros
        pagina = request.args.get('page', 1, type=int)
        filtro_estado = request.args.get('estado', '')
        filtro_prioridad = request.args.get('prioridad', '')
        
        query = db.session.query(Tickets)
        
        # Si es admin/empleado, ve todos los tickets
        if hasattr(current_user, 'id_empleado'):
            # Los empleados pueden filtrar por su asignación
            ver_asignados = request.args.get('mis_tickets', type=int)
            if ver_asignados:
                query = query.filter_by(id_empleado_asignado=current_user.id_empleado)
        # Si es cliente, ve solo sus tickets
        elif hasattr(current_user, 'id_cliente'):
            query = query.filter_by(id_cliente=current_user.id_cliente)
        else:
            return redirect(url_for('auth.login'))
        
        # Aplicar filtros
        if filtro_estado:
            query = query.filter_by(estado=filtro_estado)
        if filtro_prioridad:
            query = query.filter_by(prioridad=filtro_prioridad)
        
        tickets_list = query.order_by(desc(Tickets.fecha_creacion)).paginate(
            page=pagina, per_page=10
        )
        
        return render_template(
            'tickets/listar.html', 
            tickets=tickets_list,
            estado_filtro=filtro_estado,
            prioridad_filtro=filtro_prioridad
        )
    except Exception as e:
        flash(f'Error al cargar tickets: {str(e)}', 'danger')
        return redirect(url_for('main.index'))

# ==================== VER DETALLE DE TICKET ====================
@tickets.route('/<int:id_ticket>')
@login_required
def ver_ticket(id_ticket):
    """Ver detalle completo del ticket con todas sus respuestas"""
    try:
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            flash('Ticket no encontrado', 'danger')
            return redirect(url_for('tickets.listar_tickets'))
        
        # Verificar permisos: solo el cliente dueño o empleados pueden ver
        if hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente != current_user.id_cliente:
                flash('No tienes permiso para ver este ticket', 'danger')
                return redirect(url_for('tickets.listar_tickets'))
        
        # Obtener respuestas ordenadas por fecha
        respuestas = db.session.query(RespuestaTicket).filter_by(id_ticket=id_ticket).order_by(
            RespuestaTicket.fecha_respuesta.asc()
        ).all()
        
        # Obtener lista de empleados para asignar (solo para admin)
        empleados = db.session.query(Empleados).all() if hasattr(current_user, 'id_empleado') else []
        
        return render_template(
            'tickets/detalle.html', 
            ticket=ticket, 
            respuestas=respuestas, 
            empleados=empleados
        )
    except Exception as e:
        flash(f'Error al cargar el ticket: {str(e)}', 'danger')
        return redirect(url_for('tickets.listar_tickets'))

# ==================== CREAR TICKET (CLIENTE) ====================
@tickets.route('/crear', methods=['GET', 'POST'])
@login_required
def crear_ticket():
    """Permite a un cliente crear un nuevo ticket"""
    try:
        # Solo clientes pueden crear tickets
        if not hasattr(current_user, 'id_cliente'):
            flash('Solo los clientes pueden crear tickets', 'warning')
            return redirect(url_for('tickets.listar_tickets'))
        
        if request.method == 'POST':
            asunto = request.form.get('asunto', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            prioridad = request.form.get('prioridad', 'Media')
            
            # Validaciones
            if not asunto or len(asunto) < 5:
                flash('El asunto debe tener al menos 5 caracteres', 'warning')
                return render_template('tickets/form.html')
            
            if not descripcion or len(descripcion) < 10:
                flash('La descripción debe tener al menos 10 caracteres', 'warning')
                return render_template('tickets/form.html')
            
            # Validar prioridad
            prioridades_validas = ['Baja', 'Media', 'Alta', 'Urgente']
            if prioridad not in prioridades_validas:
                flash('Prioridad no válida', 'warning')
                return render_template('tickets/form.html')
            
            # Obtener el siguiente ID manualmente
            max_id = db.session.query(func.max(Tickets.id_ticket)).scalar()
            nuevo_id = (max_id or 0) + 1
            
            # Crear nuevo ticket con ID manual
            nuevo_ticket = Tickets(
                id_ticket=nuevo_id,
                id_cliente=current_user.id_cliente,
                asunto=asunto,
                descripcion=descripcion,
                prioridad=prioridad,
                estado='Abierto',
                fecha_creacion=datetime.now()
            )
            
            db.session.add(nuevo_ticket)
            db.session.commit()
            
            flash(f'Ticket #{nuevo_ticket.id_ticket} creado exitosamente', 'success')
            return redirect(url_for('tickets.ver_ticket', id_ticket=nuevo_ticket.id_ticket))
        
        return render_template('tickets/form.html', ticket=None)
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear ticket: {str(e)}', 'danger')
        return redirect(url_for('tickets.listar_tickets'))

# ==================== EDITAR TICKET ====================
@tickets.route('/<int:id_ticket>/editar', methods=['GET', 'POST'])
@login_required
def editar_ticket(id_ticket):
    """Editar un ticket existente"""
    try:
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            flash('Ticket no encontrado', 'danger')
            return redirect(url_for('tickets.listar_tickets'))
        
        # Verificar permisos
        if hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente != current_user.id_cliente:
                flash('No tienes permiso para editar este ticket', 'danger')
                return redirect(url_for('tickets.listar_tickets'))
            # Clientes solo pueden editar si está Abierto
            if ticket.estado != 'Abierto':
                flash('Solo puedes editar tickets en estado Abierto', 'warning')
                return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
        
        if request.method == 'POST':
            asunto = request.form.get('asunto', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            prioridad = request.form.get('prioridad', '')
            
            if not asunto or len(asunto) < 5:
                flash('El asunto debe tener al menos 5 caracteres', 'warning')
                return render_template('tickets/form.html', ticket=ticket)
            
            if not descripcion or len(descripcion) < 10:
                flash('La descripción debe tener al menos 10 caracteres', 'warning')
                return render_template('tickets/form.html', ticket=ticket)
            
            ticket.asunto = asunto
            ticket.descripcion = descripcion
            ticket.prioridad = prioridad
            
            # Solo empleados pueden cambiar estado
            if hasattr(current_user, 'id_empleado'):
                nuevo_estado = request.form.get('estado', '')
                if nuevo_estado:
                    ticket.estado = nuevo_estado
            
            ticket.fecha_actualizacion = datetime.now()
            db.session.commit()
            
            flash('Ticket actualizado exitosamente', 'success')
            return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
        
        return render_template('tickets/form.html', ticket=ticket)
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar ticket: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))

# ==================== ASIGNAR EMPLEADO (ADMIN) ====================
@tickets.route('/<int:id_ticket>/asignar', methods=['POST'])
@login_required
def asignar_empleado(id_ticket):
    """Asignar un empleado responsable al ticket"""
    try:
        # Solo empleados pueden asignar
        if not hasattr(current_user, 'id_empleado'):
            return jsonify({'success': False, 'message': 'Sin permisos'}), 403
        
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        id_empleado_asignado = request.form.get('id_empleado_asignado')
        
        if id_empleado_asignado:
            empleado = db.session.get(Empleados, id_empleado_asignado)
            if not empleado:
                flash('Empleado no encontrado', 'danger')
                return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
            
            ticket.id_empleado_asignado = id_empleado_asignado
            ticket.fecha_actualizacion = datetime.now()
            
            # Si estaba abierto, cambiar a "En Proceso"
            if ticket.estado == 'Abierto':
                ticket.estado = 'En Proceso'
            
            db.session.commit()
            flash(f'Ticket asignado a {empleado.nombres} {empleado.apellidos}', 'success')
        
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al asignar empleado: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))

# ==================== ACTUALIZAR ESTADO (ADMIN) ====================
@tickets.route('/<int:id_ticket>/actualizar-estado', methods=['POST'])
@login_required
def actualizar_estado(id_ticket):
    """Actualizar el estado del ticket"""
    try:
        # Solo empleados pueden actualizar estado
        if not hasattr(current_user, 'id_empleado'):
            return jsonify({'success': False, 'message': 'Sin permisos'}), 403
        
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        nuevo_estado = request.form.get('estado')
        
        estados_validos = ['Abierto', 'En Proceso', 'En Espera', 'Resuelto', 'Cerrado', 'Cancelado']
        if nuevo_estado not in estados_validos:
            flash('Estado no válido', 'danger')
            return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
        
        ticket.estado = nuevo_estado
        ticket.fecha_actualizacion = datetime.now()
        
        # Si se cierra, registrar fecha de cierre
        if nuevo_estado in ['Cerrado', 'Cancelado']:
            ticket.fecha_cierre = datetime.now()
        
        db.session.commit()
        flash(f'Estado actualizado a: {nuevo_estado}', 'success')
        
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar estado: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))

# ==================== AGREGAR RESPUESTA/COMENTARIO ====================
@tickets.route('/<int:id_ticket>/responder', methods=['POST'])
@login_required
def agregar_respuesta(id_ticket):
    """Agregar una respuesta o comentario al ticket"""
    try:
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        # Verificar permisos
        if hasattr(current_user, 'id_cliente'):
            if ticket.id_cliente != current_user.id_cliente:
                flash('No tienes permiso para responder este ticket', 'danger')
                return redirect(url_for('tickets.listar_tickets'))
        
        mensaje = request.form.get('mensaje', '').strip()
        es_solucion = request.form.get('es_solucion', '0')
        
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
        
        # Actualizar fecha de actualización del ticket
        ticket.fecha_actualizacion = datetime.now()
        
        # Si se marca como solución y el ticket no está cerrado, cambiarlo a "Resuelto"
        if int(es_solucion) == 1 and ticket.estado not in ['Cerrado', 'Cancelado']:
            ticket.estado = 'Resuelto'
        
        db.session.commit()
        flash('Respuesta agregada exitosamente', 'success')
        
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al agregar respuesta: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))

# ==================== CERRAR TICKET (ADMIN) ====================
@tickets.route('/<int:id_ticket>/cerrar', methods=['POST'])
@login_required
def cerrar_ticket(id_ticket):
    """Cerrar definitivamente un ticket"""
    try:
        # Solo empleados pueden cerrar tickets
        if not hasattr(current_user, 'id_empleado'):
            return jsonify({'success': False, 'message': 'Sin permisos'}), 403
        
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        ticket.estado = 'Cerrado'
        ticket.fecha_cierre = datetime.now()
        ticket.fecha_actualizacion = datetime.now()
        
        db.session.commit()
        flash(f'Ticket #{id_ticket} cerrado exitosamente', 'success')
        
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cerrar ticket: {str(e)}', 'danger')
        return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))

# ==================== ELIMINAR TICKET ====================
@tickets.route('/<int:id_ticket>/eliminar', methods=['POST'])
@login_required
def eliminar_ticket(id_ticket):
    """Eliminar ticket (solo si está Abierto o En Espera)"""
    try:
        if not hasattr(current_user, 'id_empleado'):
            return jsonify({'success': False, 'message': 'Sin permisos'}), 403
        
        ticket = db.session.get(Tickets, id_ticket)
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket no encontrado'}), 404
        
        if ticket.estado not in ['Abierto', 'En Espera']:
            flash('No se puede eliminar un ticket en este estado', 'warning')
            return redirect(url_for('tickets.ver_ticket', id_ticket=id_ticket))
        
        db.session.delete(ticket)
        db.session.commit()
        flash('Ticket eliminado exitosamente', 'success')
        
        return redirect(url_for('tickets.listar_tickets'))
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')
        return redirect(url_for('tickets.listar_tickets'))

# ==================== API ENDPOINTS ====================
@tickets.route('/api/mis-tickets', methods=['GET'])
@login_required
def api_mis_tickets():
    """API para obtener tickets del usuario actual"""
    try:
        if hasattr(current_user, 'id_empleado'):
            tickets_list = db.session.query(Tickets).filter_by(
                id_empleado_asignado=current_user.id_empleado
            ).all()
        elif hasattr(current_user, 'id_cliente'):
            tickets_list = db.session.query(Tickets).filter_by(
                id_cliente=current_user.id_cliente
            ).all()
        else:
            tickets_list = []
        
        return jsonify([{
            'id_ticket': t.id_ticket,
            'asunto': t.asunto,
            'estado': t.estado,
            'prioridad': t.prioridad,
            'fecha_creacion': t.fecha_creacion.isoformat()
        } for t in tickets_list])
    except Exception as e:
        return jsonify({'error': str(e)}), 500