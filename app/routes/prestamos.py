from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_, and_
from models import (
    Prestamos, DetallesPrestamos, Libros, Clientes, Empleados, Inventarios, Sucursales
)
from app import db
from datetime import datetime, timedelta
from decimal import Decimal

bp = Blueprint('prestamos', __name__, url_prefix='/prestamos')

# ================== FUNCIONES AUXILIARES ==================

def get_next_prestamo_id():
    """Obtiene el siguiente ID disponible para Prestamos"""
    max_id = db.session.execute(
        select(func.max(Prestamos.id_prestamo))
    ).scalar()
    return (max_id or 0) + 1

def get_next_detalle_id():
    """Obtiene el siguiente ID disponible para DetallesPrestamos"""
    max_id = db.session.execute(
        select(func.max(DetallesPrestamos.id_detalle_prestamos))
    ).scalar()
    return (max_id or 0) + 1

def calcular_fecha_devolucion(dias=14):
    """Calcula fecha de devolución estimada (por defecto 14 días)"""
    return datetime.now() + timedelta(days=dias)

def calcular_multa(fecha_devolucion_estimada, fecha_devolucion_real=None):
    """Calcula multa por días de retraso (L 5.00 por día)"""
    if not fecha_devolucion_real:
        fecha_devolucion_real = datetime.now()
    
    if isinstance(fecha_devolucion_estimada, datetime):
        fecha_devolucion_estimada = fecha_devolucion_estimada.date()
    if isinstance(fecha_devolucion_real, datetime):
        fecha_devolucion_real = fecha_devolucion_real.date()
    
    dias_retraso = (fecha_devolucion_real - fecha_devolucion_estimada).days
    
    if dias_retraso > 0:
        return Decimal(dias_retraso * 5.00)
    return Decimal(0.00)

def get_cliente_id_for_user():
    """Obtiene el ID de cliente para el usuario actual"""
    if current_user.tipo_usuario == 'cliente' and hasattr(current_user, 'id_cliente'):
        return current_user.id_cliente
    return None

# ================== FUNCIONES DE INVENTARIO AUTOMÁTICO ==================

def get_next_inventario_id():
    """Obtiene el siguiente ID disponible para Inventarios"""
    max_id = db.session.execute(
        select(func.max(Inventarios.id_inventario))
    ).scalar()
    return (max_id or 0) + 1

def get_sucursal_principal():
    """Obtiene la sucursal principal (la primera activa)"""
    sucursal = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).limit(1)
    ).scalars().first()
    
    if not sucursal:
        raise ValueError("No hay sucursales activas en el sistema")
    
    return sucursal.id_sucursal

def crear_movimiento_inventario(libro_id, sucursal_id, tipo_movimiento, cantidad, 
                                stock_anterior, stock_nuevo, empleado_id, 
                                motivo, referencia=None, observaciones=None):
    """Crear movimiento de inventario automáticamente"""
    
    movimiento = Inventarios(
        id_inventario=get_next_inventario_id(),
        id_libro=libro_id,
        id_sucursal=sucursal_id,
        tipo_movimiento=tipo_movimiento,
        cantidad=cantidad,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        formato='Físico',  # Los préstamos son siempre físicos
        fecha_movimiento=datetime.now(),
        id_empleado=empleado_id,
        motivo=motivo,
        observaciones=observaciones,
        referencia=referencia
    )
    
    db.session.add(movimiento)
    return movimiento

def registrar_salida_prestamo(libro, empleado_id, prestamo_id):
    """Registra movimiento de inventario por salida de préstamo"""
    stock_anterior = libro.stock_fisico
    libro.stock_fisico -= 1
    stock_nuevo = libro.stock_fisico
    
    sucursal_id = get_sucursal_principal()
    
    crear_movimiento_inventario(
        libro_id=libro.id_libro,
        sucursal_id=sucursal_id,
        tipo_movimiento='Salida',
        cantidad=1,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        empleado_id=empleado_id,
        motivo=f'Préstamo de libro a cliente',
        referencia=f'PRESTAMO-{prestamo_id}',
        observaciones=f'Salida automática por préstamo #{prestamo_id}'
    )

def registrar_devolucion_prestamo(libro, empleado_id, prestamo_id):
    """Registra movimiento de inventario por devolución de préstamo"""
    stock_anterior = libro.stock_fisico
    libro.stock_fisico += 1
    stock_nuevo = libro.stock_fisico
    
    sucursal_id = get_sucursal_principal()
    
    crear_movimiento_inventario(
        libro_id=libro.id_libro,
        sucursal_id=sucursal_id,
        tipo_movimiento='Devolución',
        cantidad=1,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        empleado_id=empleado_id,
        motivo=f'Devolución de libro de préstamo',
        referencia=f'DEVOLUCION-{prestamo_id}',
        observaciones=f'Entrada automática por devolución de préstamo #{prestamo_id}'
    )

# ================== CARRITO DE PRÉSTAMOS ==================

@bp.route('/carrito')
@login_required
def carrito():
    """Ver carrito de préstamos"""
    cart_ids = session.get(f'loan_cart_{current_user.id_cliente}', [])
    
    if not cart_ids:
        return render_template('prestamos/carrito.html', libros=[], total=0)
    
    libros = db.session.execute(
        select(Libros).where(Libros.id_libro.in_(cart_ids))
    ).scalars().all()
    
    total = sum([libro.precio_prestamo for libro in libros])
    
    return render_template('prestamos/carrito.html', 
                         libros=libros, 
                         total=total,
                         fecha_devolucion=calcular_fecha_devolucion())

@bp.route('/carrito/agregar/<int:libro_id>', methods=['POST'])
@login_required
def agregar_al_carrito(libro_id):
    """Agregar libro al carrito"""
    try:
        libro = db.session.get(Libros, libro_id)
        
        if not libro:
            return jsonify({'success': False, 'error': 'Libro no encontrado'}), 404
        
        if not libro.disp_prestamo:
            return jsonify({'success': False, 'error': 'Libro no disponible para préstamo'}), 400
        
        if libro.stock_fisico <= 0:
            return jsonify({'success': False, 'error': 'Sin stock disponible'}), 400
        
        cart = session.get(f'loan_cart_{current_user.id_cliente}', [])
        
        if libro_id in cart:
            return jsonify({'success': False, 'error': 'Este libro ya está en tu carrito'}), 400
        
        if len(cart) >= 5:
            return jsonify({'success': False, 'error': 'Máximo 5 libros en el carrito'}), 400
        
        cart.append(libro_id)
        session[f'loan_cart_{current_user.id_cliente}'] = cart
        session.modified = True
        
        return jsonify({
            'success': True, 
            'message': f'"{libro.titulo}" agregado al carrito',
            'cart_count': len(cart)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/carrito/eliminar/<int:libro_id>', methods=['POST'])
@login_required
def eliminar_del_carrito(libro_id):
    """Eliminar libro del carrito"""
    try:
        cart = session.get(f'loan_cart_{current_user.id_cliente}', [])
        
        if libro_id in cart:
            cart.remove(libro_id)
            session[f'loan_cart_{current_user.id_cliente}'] = cart
            session.modified = True
            
            return jsonify({
                'success': True,
                'message': 'Libro eliminado del carrito',
                'cart_count': len(cart)
            })
        
        return jsonify({'success': False, 'error': 'Libro no encontrado en el carrito'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/carrito/vaciar', methods=['POST'])
@login_required
def vaciar_carrito():
    """Vaciar carrito completo"""
    session[f'loan_cart_{current_user.id_cliente}'] = []

    session.modified = True
    return jsonify({'success': True, 'message': 'Carrito vaciado'})

@bp.route('/carrito/count')
@login_required
def carrito_count():
    """Obtener cantidad de items en el carrito"""
    cart = session.get(f'loan_cart_{current_user.id_cliente}', [])

    return jsonify({'count': len(cart)})

@bp.route('/procesar-carrito', methods=['POST'])
@login_required
def procesar_carrito():
    """Procesar préstamo desde el carrito - CON INVENTARIO AUTOMÁTICO"""
    try:
        cart_ids = session.get(f'loan_cart_{current_user.id_cliente}', [])

        observaciones = request.form.get('observaciones', '').strip()
        dias_prestamo = int(request.form.get('dias_prestamo', 14))
        
        if not cart_ids:
            flash('El carrito está vacío', 'error')
            return redirect(url_for('prestamos.carrito'))
        
        # Get cliente_id
        if current_user.tipo_usuario == 'cliente' and hasattr(current_user, 'id_cliente'):
            cliente_id = current_user.id_cliente
        else:
            flash('Solo los clientes registrados pueden solicitar préstamos desde el carrito.', 'error')
            return redirect(url_for('prestamos.carrito'))
        
        # Verificar disponibilidad de libros
        libros_a_prestar = []
        for libro_id in cart_ids:
            libro = db.session.get(Libros, int(libro_id))
            if not libro:
                flash(f'Libro con ID {libro_id} no encontrado', 'error')
                return redirect(url_for('prestamos.carrito'))
            
            if not libro.disp_prestamo:
                flash(f'El libro "{libro.titulo}" no está disponible para préstamo', 'error')
                return redirect(url_for('prestamos.carrito'))
            
            if libro.stock_fisico <= 0:
                flash(f'El libro "{libro.titulo}" no tiene stock disponible', 'error')
                return redirect(url_for('prestamos.carrito'))
            
            libros_a_prestar.append(libro)
        
        # Obtener empleado disponible
        empleado = db.session.execute(
            select(Empleados).where(Empleados.activo == 1).limit(1)
        ).scalars().first()
        
        if not empleado:
            flash('No hay empleados disponibles para procesar el préstamo. Contacta con la biblioteca.', 'error')
            return redirect(url_for('prestamos.carrito'))
        
        # Crear préstamo
        fecha_devolucion = calcular_fecha_devolucion(dias_prestamo)
        
        nuevo_prestamo = Prestamos(
            id_prestamo=get_next_prestamo_id(),
            id_cliente=cliente_id,
            id_empleado=empleado.id_empleado,
            fecha_prestamo=datetime.now(),
            fecha_devolucion_estimada=fecha_devolucion,
            estado='Activo',
            observaciones=observaciones or 'Préstamo solicitado desde el catálogo web'
        )
        
        db.session.add(nuevo_prestamo)
        
        # Crear detalles del préstamo Y MOVIMIENTOS DE INVENTARIO
        for libro in libros_a_prestar:
            detalle = DetallesPrestamos(
                id_detalle_prestamos=get_next_detalle_id(),
                id_prestamos=nuevo_prestamo.id_prestamo,
                id_libro=libro.id_libro,
                fecha_prestamo=datetime.now(),
                fecha_devolucion=fecha_devolucion,
                estado='Prestado',
                multa=Decimal(0.00)
            )
            
            db.session.add(detalle)
            
            # ✨ REGISTRAR MOVIMIENTO DE INVENTARIO AUTOMÁTICO
            registrar_salida_prestamo(libro, empleado.id_empleado, nuevo_prestamo.id_prestamo)
        
        db.session.commit()
        
        # Vaciar carrito
        session[f'loan_cart_{current_user.id_cliente}'] = []

        session.modified = True
        
        flash(f'✅ Préstamo #{nuevo_prestamo.id_prestamo} creado exitosamente. Los movimientos de inventario se registraron automáticamente.', 'success')
        return redirect(url_for('prestamos.ver', id=nuevo_prestamo.id_prestamo))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar préstamo: {str(e)}', 'error')
        return redirect(url_for('prestamos.carrito'))

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los préstamos"""
    estado = request.args.get('estado', '')
    cliente_id = request.args.get('cliente', '')
    
    query = db.session.query(Prestamos, Clientes, Empleados).join(
        Clientes, Prestamos.id_cliente == Clientes.id_cliente
    ).join(
        Empleados, Prestamos.id_empleado == Empleados.id_empleado
    )
    
    if current_user.tipo_usuario == 'cliente':
        user_cliente_id = get_cliente_id_for_user()
        if user_cliente_id:
            query = query.filter(Prestamos.id_cliente == user_cliente_id)
        else:
            query = query.filter(Prestamos.id_cliente == -1)
    
    if estado:
        query = query.filter(Prestamos.estado == estado)
    
    if cliente_id and current_user.tipo_usuario == 'admin':
        query = query.filter(Prestamos.id_cliente == int(cliente_id))
    
    query = query.order_by(Prestamos.fecha_prestamo.desc())
    
    prestamos = query.all()
    
    prestamos_data = []
    for prestamo, cliente, empleado in prestamos:
        detalles = db.session.execute(
            select(DetallesPrestamos, Libros)
            .join(Libros, DetallesPrestamos.id_libro == Libros.id_libro)
            .where(DetallesPrestamos.id_prestamos == prestamo.id_prestamo)
        ).all()
        
        multa_total = sum([det.multa or 0 for det, _ in detalles])
        
        prestamos_data.append({
            'prestamo': prestamo,
            'cliente': cliente,
            'empleado': empleado,
            'detalles': detalles,
            'multa_total': multa_total,
            'libros_count': len(detalles)
        })
    
    clientes = []
    if current_user.tipo_usuario == 'admin':
        clientes = db.session.execute(
            select(Clientes).order_by(Clientes.apellidos, Clientes.nombres)
        ).scalars().all()
    
    estados_disponibles = ['Activo', 'Devuelto', 'Atrasado', 'Cancelado']
    
    return render_template('prestamos/listar.html',
                         prestamos_data=prestamos_data,
                         clientes=clientes,
                         estados_disponibles=estados_disponibles,
                         estado_actual=estado,
                         cliente_actual=cliente_id)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalles de un préstamo"""
    resultado = db.session.execute(
        select(Prestamos, Clientes, Empleados)
        .join(Clientes, Prestamos.id_cliente == Clientes.id_cliente)
        .join(Empleados, Prestamos.id_empleado == Empleados.id_empleado)
        .where(Prestamos.id_prestamo == id)
    ).first()
    
    if not resultado:
        flash('Préstamo no encontrado', 'error')
        return redirect(url_for('prestamos.listar'))
    
    prestamo, cliente, empleado = resultado
    
    if current_user.tipo_usuario == 'cliente':
        user_cliente_id = get_cliente_id_for_user()
        if not user_cliente_id or prestamo.id_cliente != user_cliente_id:
            flash('No tienes permisos para ver este préstamo', 'error')
            return redirect(url_for('prestamos.listar'))
    
    detalles = db.session.execute(
        select(DetallesPrestamos, Libros)
        .join(Libros, DetallesPrestamos.id_libro == Libros.id_libro)
        .where(DetallesPrestamos.id_prestamos == id)
    ).all()
    
    multa_total = sum([det.multa or 0 for det, _ in detalles])
    
    return render_template('prestamos/ver.html',
                         prestamo=prestamo,
                         cliente=cliente,
                         empleado=empleado,
                         detalles=detalles,
                         multa_total=multa_total)

@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crear nuevo préstamo - CON INVENTARIO AUTOMÁTICO"""
    if current_user.tipo_usuario not in ['admin', 'empleado']:
        flash('No tienes permisos para crear préstamos. Usa el carrito de compras.', 'error')
        return redirect(url_for('libros.listar'))
    
    if request.method == 'POST':
        try:
            id_cliente = int(request.form.get('id_cliente'))
            dias_prestamo = int(request.form.get('dias_prestamo', 14))
            libros_ids = request.form.getlist('libros')
            observaciones = request.form.get('observaciones', '').strip()
            
            if not libros_ids:
                flash('Debes seleccionar al menos un libro', 'error')
                return redirect(url_for('prestamos.nuevo'))
            
            # Verificar disponibilidad de libros
            for libro_id in libros_ids:
                libro = db.session.get(Libros, int(libro_id))
                if not libro:
                    flash(f'Libro con ID {libro_id} no encontrado', 'error')
                    return redirect(url_for('prestamos.nuevo'))
                
                if not libro.disp_prestamo:
                    flash(f'El libro "{libro.titulo}" no está disponible para préstamo', 'error')
                    return redirect(url_for('prestamos.nuevo'))
                
                if libro.stock_fisico <= 0:
                    flash(f'El libro "{libro.titulo}" no tiene stock disponible', 'error')
                    return redirect(url_for('prestamos.nuevo'))
            
            # Crear préstamo
            fecha_devolucion = calcular_fecha_devolucion(dias_prestamo)
            
            nuevo_prestamo = Prestamos(
                id_prestamo=get_next_prestamo_id(),
                id_cliente=id_cliente,
                id_empleado=current_user.id_empleado,
                fecha_prestamo=datetime.now(),
                fecha_devolucion_estimada=fecha_devolucion,
                estado='Activo',
                observaciones=observaciones
            )
            
            db.session.add(nuevo_prestamo)
            
            # Crear detalles del préstamo Y MOVIMIENTOS DE INVENTARIO
            for libro_id in libros_ids:
                libro = db.session.get(Libros, int(libro_id))
                
                detalle = DetallesPrestamos(
                    id_detalle_prestamos=get_next_detalle_id(),
                    id_prestamos=nuevo_prestamo.id_prestamo,
                    id_libro=int(libro_id),
                    fecha_prestamo=datetime.now(),
                    fecha_devolucion=fecha_devolucion,
                    estado='Prestado',
                    multa=Decimal(0.00)
                )
                
                db.session.add(detalle)
                
                # ✨ REGISTRAR MOVIMIENTO DE INVENTARIO AUTOMÁTICO
                registrar_salida_prestamo(libro, current_user.id_empleado, nuevo_prestamo.id_prestamo)
            
            db.session.commit()
            
            flash(f'✅ Préstamo #{nuevo_prestamo.id_prestamo} creado exitosamente con movimientos de inventario', 'success')
            return redirect(url_for('prestamos.ver', id=nuevo_prestamo.id_prestamo))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear préstamo: {str(e)}', 'error')
            return redirect(url_for('prestamos.nuevo'))
    
    libros_disponibles = db.session.execute(
        select(Libros)
        .where(
            Libros.disp_prestamo == 1,
            Libros.stock_fisico > 0
        )
        .order_by(Libros.titulo)
    ).scalars().all()
    
    clientes = db.session.execute(
        select(Clientes)
        .order_by(Clientes.apellidos, Clientes.nombres)
    ).scalars().all()
    
    return render_template('prestamos/form.html',
                         libros=libros_disponibles,
                         clientes=clientes)

@bp.route('/devolver/<int:id>', methods=['POST'])
@login_required
def devolver(id):
    """Procesar devolución de préstamo - CON INVENTARIO AUTOMÁTICO"""
    if current_user.tipo_usuario not in ['admin', 'empleado']:
        flash('No tienes permisos para procesar devoluciones', 'error')
        return redirect(url_for('prestamos.ver', id=id))
    
    try:
        prestamo = db.session.get(Prestamos, id)
        
        if not prestamo:
            flash('Préstamo no encontrado', 'error')
            return redirect(url_for('prestamos.listar'))
        
        if prestamo.estado == 'Devuelto':
            flash('Este préstamo ya fue devuelto', 'warning')
            return redirect(url_for('prestamos.ver', id=id))
        
        libros_devueltos = request.form.getlist('libros_devueltos')
        
        if not libros_devueltos:
            flash('Debes seleccionar al menos un libro para devolver', 'error')
            return redirect(url_for('prestamos.ver', id=id))
        
        fecha_devolucion_real = datetime.now()
        todos_devueltos = True
        
        detalles = db.session.execute(
            select(DetallesPrestamos)
            .where(DetallesPrestamos.id_prestamos == id)
        ).scalars().all()
        
        for detalle in detalles:
            if str(detalle.id_libro) in libros_devueltos:
                detalle.estado = 'Devuelto'
                detalle.fecha_devolucion = fecha_devolucion_real
                
                multa = calcular_multa(
                    prestamo.fecha_devolucion_estimada,
                    fecha_devolucion_real
                )
                detalle.multa = multa
                
                # ✨ REGISTRAR MOVIMIENTO DE INVENTARIO AUTOMÁTICO
                libro = db.session.get(Libros, detalle.id_libro)
                if libro:
                    registrar_devolucion_prestamo(libro, current_user.id_empleado, prestamo.id_prestamo)
            else:
                if detalle.estado != 'Devuelto':
                    todos_devueltos = False
        
        if todos_devueltos:
            prestamo.estado = 'Devuelto'
            prestamo.fecha_devolucion_real = fecha_devolucion_real
        else:
            if datetime.now().date() > prestamo.fecha_devolucion_estimada:
                prestamo.estado = 'Atrasado'
        
        db.session.commit()
        
        flash('✅ Devolución procesada exitosamente con movimientos de inventario', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al procesar devolución: {str(e)}', 'error')
    
    return redirect(url_for('prestamos.ver', id=id))

@bp.route('/cancelar/<int:id>', methods=['POST'])
@login_required
def cancelar(id):
    """Cancelar préstamo - CON INVENTARIO AUTOMÁTICO"""
    if current_user.tipo_usuario not in ['admin', 'empleado']:
        flash('No tienes permisos para cancelar préstamos', 'error')
        return redirect(url_for('prestamos.ver', id=id))
    
    try:
        prestamo = db.session.get(Prestamos, id)
        
        if not prestamo:
            flash('Préstamo no encontrado', 'error')
            return redirect(url_for('prestamos.listar'))
        
        if prestamo.estado != 'Activo':
            flash('Solo se pueden cancelar préstamos activos', 'error')
            return redirect(url_for('prestamos.ver', id=id))
        
        detalles = db.session.execute(
            select(DetallesPrestamos, Libros)
            .join(Libros, DetallesPrestamos.id_libro == Libros.id_libro)
            .where(DetallesPrestamos.id_prestamos == id)
        ).all()
        
        for detalle, libro in detalles:
            detalle.estado = 'Cancelado'
            
            # ✨ REGISTRAR MOVIMIENTO DE INVENTARIO AUTOMÁTICO (Devolución)
            registrar_devolucion_prestamo(libro, current_user.id_empleado, prestamo.id_prestamo)
        
        prestamo.estado = 'Cancelado'
        prestamo.fecha_devolucion_real = datetime.now()
        
        db.session.commit()
        
        flash('✅ Préstamo cancelado exitosamente con movimientos de inventario', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar préstamo: {str(e)}', 'error')
    
    return redirect(url_for('prestamos.ver', id=id))

@bp.route('/renovar/<int:id>', methods=['POST'])
@login_required
def renovar(id):
    """Renovar préstamo (extender fecha de devolución)"""
    try:
        prestamo = db.session.get(Prestamos, id)
        
        if not prestamo:
            flash('Préstamo no encontrado', 'error')
            return redirect(url_for('prestamos.listar'))
        
        if current_user.tipo_usuario == 'cliente':
            user_cliente_id = get_cliente_id_for_user()
            if not user_cliente_id or prestamo.id_cliente != user_cliente_id:
                flash('No tienes permisos para renovar este préstamo', 'error')
                return redirect(url_for('prestamos.ver', id=id))
        
        if prestamo.estado not in ['Activo', 'Atrasado']:
            flash('Solo se pueden renovar préstamos activos o atrasados', 'error')
            return redirect(url_for('prestamos.ver', id=id))
        
        dias_extension = int(request.form.get('dias_extension', 7))
        
        if isinstance(prestamo.fecha_devolucion_estimada, datetime):
            nueva_fecha = prestamo.fecha_devolucion_estimada + timedelta(days=dias_extension)
        else:
            nueva_fecha = datetime.combine(prestamo.fecha_devolucion_estimada, datetime.min.time()) + timedelta(days=dias_extension)
        
        prestamo.fecha_devolucion_estimada = nueva_fecha
        prestamo.estado = 'Activo'
        
        detalles = db.session.execute(
            select(DetallesPrestamos)
            .where(
                DetallesPrestamos.id_prestamos == id,
                DetallesPrestamos.estado.in_(['Prestado', 'Atrasado'])
            )
        ).scalars().all()
        
        for detalle in detalles:
            detalle.fecha_devolucion = nueva_fecha
            detalle.estado = 'Prestado'
        
        db.session.commit()
        
        flash(f'✅ Préstamo renovado hasta {nueva_fecha.strftime("%d/%m/%Y")}', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al renovar préstamo: {str(e)}', 'error')
    
    return redirect(url_for('prestamos.ver', id=id))