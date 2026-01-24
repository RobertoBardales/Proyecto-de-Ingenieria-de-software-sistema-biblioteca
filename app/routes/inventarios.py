from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_, and_, desc, String
from models import Inventarios, Libros, Sucursales, Empleados
from app import db
from datetime import datetime

bp = Blueprint('inventarios', __name__, url_prefix='/inventarios')

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID disponible para Inventarios"""
    max_id = db.session.execute(
        select(func.max(Inventarios.id_inventario))
    ).scalar()
    return (max_id or 0) + 1

def get_empleado_para_movimiento():
    """
    Obtiene el empleado para registrar el movimiento.
    Si el usuario actual es empleado, usa su ID.
    Si es cliente o no hay empleado, usa el primer empleado activo.
    """
    if hasattr(current_user, 'id_empleado'):
        return current_user.id_empleado
    
    # Si no es empleado, buscar un empleado activo
    empleado = db.session.execute(
        select(Empleados).where(Empleados.activo == 1).limit(1)
    ).scalars().first()
    
    if not empleado:
        raise ValueError("No hay empleados activos en el sistema para registrar el movimiento")
    
    return empleado.id_empleado

def validar_movimiento_data(data, libro_id=None):
    """Valida los datos del movimiento de inventario"""
    errors = []
    
    # Validar libro
    if not libro_id and not data.get('id_libro'):
        errors.append('Debe seleccionar un libro')
    
    # Validar sucursal
    if not data.get('id_sucursal'):
        errors.append('Debe seleccionar una sucursal')
    
    # Validar tipo de movimiento
    tipo_movimiento = data.get('tipo_movimiento', '').strip()
    tipos_validos = ['Entrada', 'Salida', 'Ajuste', 'Transferencia', 'Devolución']
    if tipo_movimiento not in tipos_validos:
        errors.append('Tipo de movimiento inválido')
    
    # Validar formato
    formato = data.get('formato', '').strip()
    formatos_validos = ['Físico', 'Digital']
    if formato not in formatos_validos:
        errors.append('Formato inválido')
    
    # Validar cantidad
    try:
        cantidad = int(data.get('cantidad', 0))
        if cantidad <= 0:
            errors.append('La cantidad debe ser mayor a 0')
    except ValueError:
        errors.append('Cantidad inválida')
    
    # Validar motivo
    motivo = data.get('motivo', '').strip()
    if not motivo or len(motivo) < 10:
        errors.append('El motivo debe tener al menos 10 caracteres')
    
    return errors

def calcular_nuevo_stock(libro, formato, tipo_movimiento, cantidad):
    """Calcula el nuevo stock después de un movimiento"""
    if formato == 'Físico':
        stock_actual = libro.stock_fisico
    else:
        stock_actual = libro.stock_digital
    
    if tipo_movimiento in ['Entrada', 'Devolución']:
        nuevo_stock = stock_actual + cantidad
    elif tipo_movimiento in ['Salida', 'Transferencia']:
        nuevo_stock = stock_actual - cantidad
        if nuevo_stock < 0:
            raise ValueError(f'Stock insuficiente. Stock actual: {stock_actual}')
    else:  # Ajuste
        nuevo_stock = cantidad
    
    return stock_actual, nuevo_stock

# ================== RUTAS CRUD - SIN RESTRICCIONES DE ROL ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los movimientos de inventario - ACCESO PARA TODOS"""
    # Get filter parameters
    busqueda = request.args.get('busqueda', '').strip()
    sucursal = request.args.get('sucursal', '').strip()
    tipo_movimiento = request.args.get('tipo_movimiento', '').strip()
    formato = request.args.get('formato', '').strip()
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    libro_id = request.args.get('libro_id', '').strip()
    
    # Base query with relationships
    query = db.session.query(Inventarios).join(Libros).join(Sucursales)
    
    # Apply search filter - FIXED for SQL Server TEXT fields
    if busqueda:
        search_term = f'%{busqueda}%'
        # Use CAST to convert TEXT to VARCHAR for SQL Server compatibility
        query = query.filter(
            or_(
                Libros.titulo.ilike(search_term),
                Libros.isbn.ilike(search_term),
                Inventarios.referencia.ilike(search_term),
                # Cast TEXT fields to VARCHAR before using LOWER
                func.cast(Inventarios.motivo, String).ilike(search_term),
                func.cast(Inventarios.observaciones, String).ilike(search_term)
            )
        )
    
    # Filter by libro
    if libro_id:
        query = query.filter(Inventarios.id_libro == int(libro_id))
    
    # Filter by sucursal
    if sucursal:
        query = query.filter(Inventarios.id_sucursal == int(sucursal))
    
    # Filter by tipo_movimiento
    if tipo_movimiento:
        query = query.filter(Inventarios.tipo_movimiento == tipo_movimiento)
    
    # Filter by formato
    if formato:
        query = query.filter(Inventarios.formato == formato)
    
    # Filter by date range
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d')
            query = query.filter(Inventarios.fecha_movimiento >= fecha_desde_dt)
        except ValueError:
            flash('Fecha desde inválida', 'warning')
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d')
            # Add one day to include the entire end date
            fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Inventarios.fecha_movimiento <= fecha_hasta_dt)
        except ValueError:
            flash('Fecha hasta inválida', 'warning')
    
    # Order by most recent first
    query = query.order_by(desc(Inventarios.fecha_movimiento))
    
    movimientos = query.all()
    
    # DEBUG: Print to console if search is active
    if busqueda:
        print(f"🔍 Searching for: '{busqueda}'")
        print(f"📊 Found {len(movimientos)} movements")
        if len(movimientos) > 0:
            print(f"📦 First result: {movimientos[0].referencia} - {movimientos[0].motivo}")
    
    # Get all sucursales for filter
    todas_sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    tipos_movimiento_disponibles = ['Entrada', 'Salida', 'Ajuste', 'Transferencia', 'Devolución']
    formatos_disponibles = ['Físico', 'Digital']
    
    return render_template('inventarios/listar.html',
                         movimientos=movimientos,
                         todas_sucursales=todas_sucursales,
                         tipos_movimiento_disponibles=tipos_movimiento_disponibles,
                         formatos_disponibles=formatos_disponibles,
                         busqueda_actual=busqueda,
                         sucursal_actual=sucursal,
                         tipo_movimiento_actual=tipo_movimiento,
                         formato_actual=formato,
                         fecha_desde_actual=fecha_desde,
                         fecha_hasta_actual=fecha_hasta,
                         libro_id_actual=libro_id)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalles de un movimiento de inventario - ACCESO PARA TODOS"""
    movimiento = db.session.get(Inventarios, id)
    
    if not movimiento:
        flash('Movimiento no encontrado', 'error')
        return redirect(url_for('inventarios.listar'))
    
    # Get related data
    libro = db.session.get(Libros, movimiento.id_libro)
    sucursal = db.session.get(Sucursales, movimiento.id_sucursal)
    empleado = db.session.get(Empleados, movimiento.id_empleado)
    
    return render_template('inventarios/ver.html',
                         movimiento=movimiento,
                         libro=libro,
                         sucursal=sucursal,
                         empleado=empleado)

@bp.route('/nuevo', methods=['GET', 'POST'])
@bp.route('/nuevo/<int:libro_id>', methods=['GET', 'POST'])
@login_required
def nuevo(libro_id=None):
    """Crear nuevo movimiento de inventario - ACCESO PARA TODOS"""
    if request.method == 'POST':
        try:
            # Get libro_id from form if not in URL
            final_libro_id = libro_id or request.form.get('id_libro')
            
            # Validate data
            errors = validar_movimiento_data(request.form, final_libro_id)
            if errors:
                for error in errors:
                    flash(error, 'error')
                return redirect(url_for('inventarios.nuevo', libro_id=libro_id))
            
            # Get libro
            libro = db.session.get(Libros, int(final_libro_id))
            if not libro:
                flash('Libro no encontrado', 'error')
                return redirect(url_for('inventarios.listar'))
            
            # Calculate new stock
            tipo_movimiento = request.form.get('tipo_movimiento')
            formato = request.form.get('formato')
            cantidad = int(request.form.get('cantidad'))
            
            try:
                stock_anterior, stock_nuevo = calcular_nuevo_stock(
                    libro, formato, tipo_movimiento, cantidad
                )
            except ValueError as e:
                flash(str(e), 'error')
                return redirect(url_for('inventarios.nuevo', libro_id=libro_id))
            
            # Get empleado ID (works for both empleados and clientes)
            empleado_id = get_empleado_para_movimiento()
            
            # Create movement
            nuevo_movimiento = Inventarios(
                id_inventario=get_next_id(),
                id_libro=int(final_libro_id),
                id_sucursal=int(request.form.get('id_sucursal')),
                tipo_movimiento=tipo_movimiento,
                cantidad=cantidad,
                stock_anterior=stock_anterior,
                stock_nuevo=stock_nuevo,
                formato=formato,
                fecha_movimiento=datetime.now(),
                id_empleado=empleado_id,
                motivo=request.form.get('motivo', '').strip(),
                observaciones=request.form.get('observaciones', '').strip(),
                referencia=request.form.get('referencia', '').strip()
            )
            
            db.session.add(nuevo_movimiento)
            
            # Update libro stock
            if formato == 'Físico':
                libro.stock_fisico = stock_nuevo
            else:
                libro.stock_digital = stock_nuevo
            
            db.session.commit()
            
            flash(f'✅ Movimiento de inventario registrado exitosamente', 'success')
            return redirect(url_for('inventarios.ver', id=nuevo_movimiento.id_inventario))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear movimiento: {str(e)}', 'error')
            return redirect(url_for('inventarios.nuevo', libro_id=libro_id))
    
    # GET - Load form data
    libros = db.session.execute(
        select(Libros).order_by(Libros.titulo)
    ).scalars().all()
    
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    tipos_movimiento = ['Entrada', 'Salida', 'Ajuste', 'Transferencia', 'Devolución']
    formatos = ['Físico', 'Digital']
    
    # Pre-select libro if libro_id provided
    libro_seleccionado = None
    if libro_id:
        libro_seleccionado = db.session.get(Libros, libro_id)
    
    return render_template('inventarios/form.html',
                         libros=libros,
                         sucursales=sucursales,
                         tipos_movimiento=tipos_movimiento,
                         formatos=formatos,
                         libro_seleccionado=libro_seleccionado)

@bp.route('/libro/<int:libro_id>')
@login_required
def historial_libro(libro_id):
    """Ver historial de movimientos de un libro específico - ACCESO PARA TODOS"""
    libro = db.session.get(Libros, libro_id)
    if not libro:
        flash('Libro no encontrado', 'error')
        return redirect(url_for('libros.listar'))
    
    # Get all movements for this libro
    movimientos = db.session.execute(
        select(Inventarios)
        .where(Inventarios.id_libro == libro_id)
        .order_by(desc(Inventarios.fecha_movimiento))
    ).scalars().all()
    
    # Calculate statistics
    total_entradas_fisico = db.session.execute(
        select(func.sum(Inventarios.cantidad))
        .where(
            and_(
                Inventarios.id_libro == libro_id,
                Inventarios.formato == 'Físico',
                Inventarios.tipo_movimiento.in_(['Entrada', 'Devolución'])
            )
        )
    ).scalar() or 0
    
    total_salidas_fisico = db.session.execute(
        select(func.sum(Inventarios.cantidad))
        .where(
            and_(
                Inventarios.id_libro == libro_id,
                Inventarios.formato == 'Físico',
                Inventarios.tipo_movimiento.in_(['Salida', 'Transferencia'])
            )
        )
    ).scalar() or 0
    
    total_entradas_digital = db.session.execute(
        select(func.sum(Inventarios.cantidad))
        .where(
            and_(
                Inventarios.id_libro == libro_id,
                Inventarios.formato == 'Digital',
                Inventarios.tipo_movimiento.in_(['Entrada', 'Devolución'])
            )
        )
    ).scalar() or 0
    
    total_salidas_digital = db.session.execute(
        select(func.sum(Inventarios.cantidad))
        .where(
            and_(
                Inventarios.id_libro == libro_id,
                Inventarios.formato == 'Digital',
                Inventarios.tipo_movimiento.in_(['Salida', 'Transferencia'])
            )
        )
    ).scalar() or 0
    
    estadisticas = {
        'entradas_fisico': total_entradas_fisico,
        'salidas_fisico': total_salidas_fisico,
        'entradas_digital': total_entradas_digital,
        'salidas_digital': total_salidas_digital,
        'stock_fisico_actual': libro.stock_fisico,
        'stock_digital_actual': libro.stock_digital
    }
    
    return render_template('inventarios/historial_libro.html',
                         libro=libro,
                         movimientos=movimientos,
                         estadisticas=estadisticas)

@bp.route('/reporte')
@login_required
def reporte():
    """Generar reporte de inventario por sucursal - ACCESO PARA TODOS"""
    sucursal_id = request.args.get('sucursal_id', '').strip()
    
    # Get all active sucursales
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    reporte_data = None
    sucursal_seleccionada = None
    
    if sucursal_id:
        sucursal_seleccionada = db.session.get(Sucursales, int(sucursal_id))
        
        # Get latest inventory movement for each book in this sucursal
        # This gives us the current stock per book per sucursal
        subquery = (
            select(
                Inventarios.id_libro,
                func.max(Inventarios.fecha_movimiento).label('max_fecha')
            )
            .where(Inventarios.id_sucursal == int(sucursal_id))
            .group_by(Inventarios.id_libro)
        ).subquery()
        
        movimientos_recientes = db.session.execute(
            select(Inventarios, Libros)
            .join(Libros, Inventarios.id_libro == Libros.id_libro)
            .join(
                subquery,
                and_(
                    Inventarios.id_libro == subquery.c.id_libro,
                    Inventarios.fecha_movimiento == subquery.c.max_fecha
                )
            )
            .where(Inventarios.id_sucursal == int(sucursal_id))
            .order_by(Libros.titulo)
        ).all()
        
        reporte_data = movimientos_recientes
    
    return render_template('inventarios/reporte.html',
                         sucursales=sucursales,
                         sucursal_seleccionada=sucursal_seleccionada,
                         reporte_data=reporte_data,
                         sucursal_id_actual=sucursal_id)