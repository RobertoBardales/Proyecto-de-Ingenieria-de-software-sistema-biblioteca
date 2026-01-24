from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_, and_, desc
from models import (OrdenCompra, DetalleOrdenCompra, RecepcionCompra, DetalleRecepcionCompra,
                   Editoriales, Libros, Sucursales, Empleados, Inventarios, PrecioCompraEditorial,
                   LibroEditoriales)
from app import db
from datetime import datetime, timedelta
from decimal import Decimal
import traceback

bp = Blueprint('orden_compra', __name__, url_prefix='/ordenes-compra')

# ================== CONSTANTES ==================

ESTADOS_ORDEN = ['Pendiente', 'Aprobada', 'En Tránsito', 'En Recepción', 'Recibida', 'Cancelada']
ESTADOS_LINEA = ['Pendiente', 'Recibido Parcial', 'Recibido Completo', 'Rechazado']
ESTADOS_RECEPCION = ['Aceptado', 'Aceptado con Observaciones', 'Rechazado']
ESTADOS_PRODUCTO = ['Bueno', 'Dañado', 'Defectuoso']
FORMATOS = ['Físico', 'Digital']

# Porcentaje para calcular precio de compra por defecto (50% del precio de venta)
DESCUENTO_COMPRA_DEFAULT = Decimal('0.50')

# ================== FUNCIONES AUXILIARES ==================

def get_next_orden_id():
    """Obtiene el siguiente ID para orden de compra"""
    max_id = db.session.execute(
        select(func.max(OrdenCompra.id_orden))
    ).scalar()
    return (max_id or 0) + 1

def get_next_detalle_orden_id():
    """Obtiene el siguiente ID para detalle de orden"""
    max_id = db.session.execute(
        select(func.max(DetalleOrdenCompra.id_detalle_orden))
    ).scalar()
    return (max_id or 0) + 1

def get_next_recepcion_id():
    """Obtiene el siguiente ID para recepción"""
    max_id = db.session.execute(
        select(func.max(RecepcionCompra.id_recepcion))
    ).scalar()
    return (max_id or 0) + 1

def get_next_detalle_recepcion_id():
    """Obtiene el siguiente ID para detalle de recepción"""
    max_id = db.session.execute(
        select(func.max(DetalleRecepcionCompra.id_detalle_recepcion))
    ).scalar()
    return (max_id or 0) + 1

def generar_numero_orden():
    """Genera número de orden único: OC-YYYY-NNNN"""
    año_actual = datetime.now().year
    
    # Contar órdenes del año actual
    count = db.session.execute(
        select(func.count(OrdenCompra.id_orden))
        .where(func.year(OrdenCompra.fecha_solicitud) == año_actual)
    ).scalar() or 0
    
    return f"OC-{año_actual}-{count + 1:04d}"

def generar_referencia():
    """Genera referencia única automática: OC-YYYYMMDDHHMMSS"""
    return f"OC-{datetime.now().strftime('%Y%m%d%H%M%S')}"

def obtener_precio_compra(id_libro, id_editorial):
    """
    Obtiene el precio de compra de un libro para una editorial específica.
    Si existe en la tabla PrecioCompraEditorial, usa ese precio.
    Si no, retorna None (no se permite ordenar sin precio configurado).
    """
    precio = db.session.execute(
        select(PrecioCompraEditorial)
        .where(
            and_(
                PrecioCompraEditorial.id_libro == id_libro,
                PrecioCompraEditorial.id_editorial == id_editorial,
                PrecioCompraEditorial.activo == 1
            )
        )
    ).scalars().first()
    
    if precio:
        return precio.precio_compra
    
    # Si no hay precio definido, retornar None
    # No usamos precio por defecto para evitar errores
    return None

def calcular_totales_orden(detalles):
    """Calcula subtotal, ISV y total de una orden"""
    subtotal = sum(d['precio_unitario'] * d['cantidad'] for d in detalles)
    isv = subtotal * Decimal('0.15')  # 15% ISV
    total = subtotal + isv
    
    return {
        'subtotal': subtotal,
        'isv': isv,
        'total': total
    }

def actualizar_estado_orden(orden_id):
    """Actualiza el estado de la orden basado en el estado de sus líneas"""
    orden = db.session.get(OrdenCompra, orden_id)
    if not orden or orden.estado == 'Cancelada':
        return
    
    detalles = orden.Detalle_Orden_Compra
    
    if not detalles:
        return
    
    estados = [d.estado_linea for d in detalles]
    
    # Si todos están completamente recibidos
    if all(e == 'Recibido Completo' for e in estados):
        orden.estado = 'Recibida'
        orden.fecha_recepcion = datetime.now()
    # Si al menos uno está recibido (parcial o completo)
    elif any(e in ['Recibido Parcial', 'Recibido Completo'] for e in estados):
        if orden.estado not in ['En Recepción', 'En Tránsito']:
            orden.estado = 'En Recepción'  # Changed from 'En Tránsito'
    
    db.session.commit()

def crear_movimiento_inventario(detalle_orden, cantidad_recibida, sucursal_id, empleado_id, referencia):
    """Crea movimiento de inventario al recepcionar productos"""
    libro = detalle_orden.Libros_
    formato = detalle_orden.formato
    
    # Get current stock BEFORE any changes
    if formato == 'Físico':
        stock_anterior = libro.stock_fisico
    else:
        stock_anterior = libro.stock_digital
    
    # Calculate new stock
    stock_nuevo = stock_anterior + cantidad_recibida
    
    # Get next inventory ID
    max_inv_id = db.session.execute(
        select(func.max(Inventarios.id_inventario))
    ).scalar()
    nuevo_inv_id = (max_inv_id or 0) + 1
    
    # Create inventory movement record
    movimiento = Inventarios(
        id_inventario=nuevo_inv_id,
        id_libro=detalle_orden.id_libro,
        id_sucursal=sucursal_id,
        tipo_movimiento='Entrada',
        cantidad=cantidad_recibida,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        formato=formato,
        fecha_movimiento=datetime.now(),
        id_empleado=empleado_id,
        motivo=f'Recepción de orden de compra {referencia}',
        observaciones=f'Proveedor: {detalle_orden.Orden_Compra_.Editoriales_.nombre}. Orden: {detalle_orden.Orden_Compra_.numero_orden}',
        referencia=referencia
    )
    
    db.session.add(movimiento)
    
    # UPDATE the book's stock AFTER creating the movement
    if formato == 'Físico':
        libro.stock_fisico = stock_nuevo
    else:
        libro.stock_digital = stock_nuevo
    
    # DEBUG: Print what we're creating
    print(f"📦 Creating inventory movement:")
    print(f"   Book: {libro.titulo}")
    print(f"   Format: {formato}")
    print(f"   Quantity: {cantidad_recibida}")
    print(f"   Stock: {stock_anterior} → {stock_nuevo}")
    print(f"   Reference: {referencia}")

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todas las órdenes de compra"""
    # Filtros
    estado = request.args.get('estado', '').strip()
    editorial = request.args.get('editorial', '').strip()
    sucursal = request.args.get('sucursal', '').strip()
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    busqueda = request.args.get('busqueda', '').strip()
    
    # Query base
    query = db.session.query(OrdenCompra).join(Editoriales).join(Sucursales)
    
    # Aplicar filtros
    if estado:
        query = query.filter(OrdenCompra.estado == estado)
    
    if editorial:
        query = query.filter(OrdenCompra.id_editorial == int(editorial))
    
    if sucursal:
        query = query.filter(OrdenCompra.id_sucursal == int(sucursal))
    
    if busqueda:
        search_term = f'%{busqueda}%'
        query = query.filter(
            or_(
                OrdenCompra.numero_orden.ilike(search_term),
                OrdenCompra.referencia.ilike(search_term),
                OrdenCompra.motivo.ilike(search_term)
            )
        )
    
    if fecha_desde:
        try:
            fecha_desde_dt = datetime.strptime(fecha_desde, '%Y-%m-%d')
            query = query.filter(OrdenCompra.fecha_solicitud >= fecha_desde_dt)
        except ValueError:
            flash('Fecha desde inválida', 'warning')
    
    if fecha_hasta:
        try:
            fecha_hasta_dt = datetime.strptime(fecha_hasta, '%Y-%m-%d')
            fecha_hasta_dt = fecha_hasta_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(OrdenCompra.fecha_solicitud <= fecha_hasta_dt)
        except ValueError:
            flash('Fecha hasta inválida', 'warning')
    
    ordenes = query.order_by(desc(OrdenCompra.fecha_solicitud)).all()
    
    # Datos para filtros
    editoriales = db.session.execute(
        select(Editoriales).order_by(Editoriales.nombre)
    ).scalars().all()
    
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    return render_template('orden_compra/listar.html',
                         ordenes=ordenes,
                         estados=ESTADOS_ORDEN,
                         editoriales=editoriales,
                         sucursales=sucursales,
                         estado_actual=estado,
                         editorial_actual=editorial,
                         sucursal_actual=sucursal,
                         fecha_desde_actual=fecha_desde,
                         fecha_hasta_actual=fecha_hasta,
                         busqueda_actual=busqueda)

@bp.route('/nueva', methods=['GET', 'POST'])
@login_required
def nueva():
    """Crear nueva orden de compra"""
    if request.method == 'POST':
        try:
            # Validar editorial
            id_editorial = request.form.get('id_editorial')
            if not id_editorial:
                flash('❌ Debe seleccionar una editorial', 'error')
                return redirect(url_for('orden_compra.nueva'))
            
            editorial = db.session.get(Editoriales, int(id_editorial))
            if not editorial:
                flash('❌ Editorial no encontrada', 'error')
                return redirect(url_for('orden_compra.nueva'))
            
            # Validar sucursal
            id_sucursal = request.form.get('id_sucursal')
            if not id_sucursal:
                flash('❌ Debe seleccionar una sucursal', 'error')
                return redirect(url_for('orden_compra.nueva'))
            
            # Obtener detalles del formulario
            libros_ids = request.form.getlist('libro_id[]')
            cantidades = request.form.getlist('cantidad[]')
            precios_unitarios = request.form.getlist('precio_unitario[]')
            formatos = request.form.getlist('formato[]')
            
            if not libros_ids or len(libros_ids) == 0:
                flash('❌ Debe agregar al menos un libro a la orden', 'error')
                return redirect(url_for('orden_compra.nueva'))
            
            # Preparar detalles y VALIDAR precios
            detalles_data = []
            libros_sin_precio = []
            
            for i in range(len(libros_ids)):
                if libros_ids[i] and cantidades[i]:
                    libro = db.session.get(Libros, int(libros_ids[i]))
                    if not libro:
                        continue
                    
                    # VALIDACIÓN CRÍTICA: Verificar que el precio venga del formulario
                    # y que corresponda con el precio configurado
                    precio_form = Decimal(precios_unitarios[i]) if precios_unitarios[i] else Decimal('0')
                    
                    # Obtener precio configurado de la tabla
                    precio_configurado = obtener_precio_compra(int(libros_ids[i]), int(id_editorial))
                    
                    if precio_configurado is None:
                        libros_sin_precio.append(libro.titulo)
                        continue
                    
                    # Validar que el precio del formulario coincida con el configurado
                    # (con margen de error de 0.01 por redondeos)
                    if abs(precio_form - precio_configurado) > Decimal('0.01'):
                        flash(f'❌ El precio del libro "{libro.titulo}" no coincide con el precio configurado', 'error')
                        return redirect(url_for('orden_compra.nueva'))
                    
                    detalles_data.append({
                        'id_libro': int(libros_ids[i]),
                        'cantidad': int(cantidades[i]),
                        'precio_unitario': precio_configurado,  # Usar precio configurado
                        'formato': formatos[i]
                    })
            
            # Si hay libros sin precio configurado, rechazar la orden
            if libros_sin_precio:
                flash(f'❌ Los siguientes libros no tienen precio configurado: {", ".join(libros_sin_precio)}. Configure los precios antes de crear la orden.', 'error')
                return redirect(url_for('orden_compra.nueva'))
            
            if not detalles_data:
                flash('❌ No se pudieron procesar los detalles de la orden', 'error')
                return redirect(url_for('orden_compra.nueva'))
            
            totales = calcular_totales_orden(detalles_data)
            
            # Obtener empleado actual
            if hasattr(current_user, 'id_empleado'):
                id_empleado = current_user.id_empleado
            else:
                # Si es cliente, usar primer empleado activo
                empleado = db.session.execute(
                    select(Empleados).where(Empleados.activo == 1).limit(1)
                ).scalars().first()
                if not empleado:
                    flash('❌ No hay empleados activos para registrar la orden', 'error')
                    return redirect(url_for('orden_compra.nueva'))
                id_empleado = empleado.id_empleado
            
            # Crear orden
            nueva_orden = OrdenCompra(
                id_orden=get_next_orden_id(),
                id_editorial=int(id_editorial),
                id_sucursal=int(id_sucursal),
                id_empleado_solicitante=id_empleado,
                numero_orden=generar_numero_orden(),
                fecha_solicitud=datetime.now(),
                fecha_entrega_estimada=datetime.strptime(request.form.get('fecha_entrega_estimada'), '%Y-%m-%d'),
                estado='Pendiente',
                subtotal=totales['subtotal'],
                isv=totales['isv'],
                total=totales['total'],
                motivo=request.form.get('motivo', '').strip(),
                referencia=generar_referencia(),
                observaciones=request.form.get('observaciones', '').strip()
            )
            
            db.session.add(nueva_orden)
            db.session.flush()  # Para obtener el ID
            
            # Crear detalles
            for detalle_data in detalles_data:
                subtotal_linea = detalle_data['precio_unitario'] * detalle_data['cantidad']
                
                detalle = DetalleOrdenCompra(
                    id_detalle_orden=get_next_detalle_orden_id(),
                    id_orden=nueva_orden.id_orden,
                    id_libro=detalle_data['id_libro'],
                    cantidad_ordenada=detalle_data['cantidad'],
                    cantidad_recibida=0,
                    precio_unitario=detalle_data['precio_unitario'],
                    subtotal=subtotal_linea,
                    formato=detalle_data['formato'],
                    estado_linea='Pendiente'
                )
                db.session.add(detalle)
            
            db.session.commit()
            
            flash(f'✅ Orden de compra {nueva_orden.numero_orden} creada exitosamente', 'success')
            return redirect(url_for('orden_compra.ver', id=nueva_orden.id_orden))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error al crear orden: {str(e)}', 'error')
            print(f"Error creating order: {str(e)}")
            traceback.print_exc()
            return redirect(url_for('orden_compra.nueva'))
    
    # GET - Cargar datos del formulario
    editoriales = db.session.execute(
        select(Editoriales).order_by(Editoriales.nombre)
    ).scalars().all()
    
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    # Fecha estimada por defecto: 15 días
    fecha_estimada = (datetime.now() + timedelta(days=15)).strftime('%Y-%m-%d')
    
    return render_template('orden_compra/form.html',
                         editoriales=editoriales,
                         sucursales=sucursales,
                         formatos=FORMATOS,
                         fecha_estimada=fecha_estimada)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalles de una orden de compra"""
    orden = db.session.get(OrdenCompra, id)
    
    if not orden:
        flash('Orden no encontrada', 'error')
        return redirect(url_for('orden_compra.listar'))
    
    # Calcular estadísticas
    total_items = sum(d.cantidad_ordenada for d in orden.Detalle_Orden_Compra)
    total_recibidos = sum(d.cantidad_recibida for d in orden.Detalle_Orden_Compra)
    porcentaje_recibido = (total_recibidos / total_items * 100) if total_items > 0 else 0
    
    # Obtener recepciones
    recepciones = db.session.execute(
        select(RecepcionCompra)
        .where(RecepcionCompra.id_orden == id)
        .order_by(desc(RecepcionCompra.fecha_recepcion))
    ).scalars().all()
    
    return render_template('orden_compra/ver.html',
                         orden=orden,
                         total_items=total_items,
                         total_recibidos=total_recibidos,
                         porcentaje_recibido=porcentaje_recibido,
                         recepciones=recepciones,
                         estados_orden=ESTADOS_ORDEN)

@bp.route('/aprobar/<int:id>', methods=['POST'])
@login_required
def aprobar(id):
    """Aprobar una orden de compra"""
    try:
        orden = db.session.get(OrdenCompra, id)
        
        if not orden:
            flash('Orden no encontrada', 'error')
            return redirect(url_for('orden_compra.listar'))
        
        if orden.estado != 'Pendiente':
            flash('Solo se pueden aprobar órdenes pendientes', 'warning')
            return redirect(url_for('orden_compra.ver', id=id))
        
        orden.estado = 'Aprobada'
        db.session.commit()
        
        flash(f'✅ Orden {orden.numero_orden} aprobada exitosamente', 'success')
        return redirect(url_for('orden_compra.ver', id=id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al aprobar orden: {str(e)}', 'error')
        return redirect(url_for('orden_compra.ver', id=id))

@bp.route('/marcar-transito/<int:id>', methods=['POST'])
@login_required
def marcar_transito(id):
    """Marca la orden como En Tránsito (útil para testing)"""
    try:
        orden = db.session.get(OrdenCompra, id)
        
        if not orden:
            flash('Orden no encontrada', 'error')
            return redirect(url_for('orden_compra.listar'))
        
        if orden.estado != 'Aprobada':
            flash('Solo se pueden marcar en tránsito órdenes aprobadas', 'warning')
            return redirect(url_for('orden_compra.ver', id=id))
        
        orden.estado = 'En Tránsito'
        db.session.commit()
        
        flash(f'✅ Orden {orden.numero_orden} marcada como En Tránsito. Ya puede recepcionarla.', 'success')
        return redirect(url_for('orden_compra.ver', id=id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al marcar orden: {str(e)}', 'error')
        return redirect(url_for('orden_compra.ver', id=id))

@bp.route('/cancelar/<int:id>', methods=['GET', 'POST'])
@login_required
def cancelar(id):
    """Cancelar una orden de compra"""
    orden = db.session.get(OrdenCompra, id)
    
    if not orden:
        flash('Orden no encontrada', 'error')
        return redirect(url_for('orden_compra.listar'))
    
    if orden.estado == 'Cancelada':
        flash('Esta orden ya está cancelada', 'warning')
        return redirect(url_for('orden_compra.ver', id=id))
    
    if orden.estado == 'Recibida':
        flash('No se puede cancelar una orden que ya fue recibida', 'error')
        return redirect(url_for('orden_compra.ver', id=id))
    
    if request.method == 'POST':
        try:
            motivo_cancelacion = request.form.get('motivo_cancelacion', '').strip()
            
            if not motivo_cancelacion or len(motivo_cancelacion) < 10:
                flash('Debe proporcionar un motivo de cancelación (mínimo 10 caracteres)', 'error')
                return redirect(url_for('orden_compra.cancelar', id=id))
            
            orden.estado = 'Cancelada'
            orden.fecha_cancelacion = datetime.now()
            orden.motivo_cancelacion = motivo_cancelacion
            
            db.session.commit()
            
            flash(f'✅ Orden {orden.numero_orden} cancelada exitosamente', 'success')
            return redirect(url_for('orden_compra.ver', id=id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al cancelar orden: {str(e)}', 'error')
            return redirect(url_for('orden_compra.ver', id=id))
    
    return render_template('orden_compra/cancelar.html', orden=orden)

@bp.route('/recepcionar/<int:id>', methods=['GET', 'POST'])
@login_required
def recepcionar(id):
    """Recepcionar productos de una orden de compra"""
    orden = db.session.get(OrdenCompra, id)
    
    if not orden:
        flash('Orden no encontrada', 'error')
        return redirect(url_for('orden_compra.listar'))
    
    if orden.estado not in ['Aprobada', 'En Tránsito', 'En Recepción']:
        flash('Solo se pueden recepcionar órdenes aprobadas o en tránsito', 'warning')
        return redirect(url_for('orden_compra.ver', id=id))
    
    if request.method == 'POST':
        try:
            # Validar que al menos una línea tenga productos recibidos o rechazados
            detalles_ids = request.form.getlist('detalle_id[]')
            cantidades_recibidas = request.form.getlist('cantidad_recibida[]')
            cantidades_rechazadas = request.form.getlist('cantidad_rechazada[]')
            estados_producto = request.form.getlist('estado_producto[]')
            observaciones_detalle = request.form.getlist('observaciones_detalle[]')
            
            # VALIDACIÓN 1: Verificar que hay al menos un movimiento
            tiene_movimiento = False
            for i in range(len(detalles_ids)):
                cant_recibida = int(cantidades_recibidas[i]) if cantidades_recibidas[i] else 0
                cant_rechazada = int(cantidades_rechazadas[i]) if cantidades_rechazadas[i] else 0
                if cant_recibida > 0 or cant_rechazada > 0:
                    tiene_movimiento = True
                    break
            
            if not tiene_movimiento:
                flash('❌ Debe recepcionar o rechazar al menos un producto', 'error')
                return redirect(url_for('orden_compra.recepcionar', id=id))
            
            # VALIDACIÓN 2: Verificar cantidades por línea
            errores_validacion = []
            for i in range(len(detalles_ids)):
                detalle_orden = db.session.get(DetalleOrdenCompra, int(detalles_ids[i]))
                if not detalle_orden:
                    continue
                
                cant_recibida = int(cantidades_recibidas[i]) if cantidades_recibidas[i] else 0
                cant_rechazada = int(cantidades_rechazadas[i]) if cantidades_rechazadas[i] else 0
                pendiente = detalle_orden.cantidad_ordenada - detalle_orden.cantidad_recibida
                
                # Validar que no exceda el pendiente
                total_procesado = cant_recibida + cant_rechazada
                if total_procesado > pendiente:
                    errores_validacion.append(
                        f'"{detalle_orden.Libros_.titulo}": Total procesado ({total_procesado}) '
                        f'excede el pendiente ({pendiente})'
                    )
                
                # Validar que si hay cantidad, debe haber un estado válido
                if cant_recibida > 0 or cant_rechazada > 0:
                    if not estados_producto[i] or estados_producto[i] not in ESTADOS_PRODUCTO:
                        errores_validacion.append(
                            f'"{detalle_orden.Libros_.titulo}": Debe seleccionar un estado de producto válido'
                        )
                    
                    # Si hay productos rechazados, debe haber observaciones
                    if cant_rechazada > 0 and (not observaciones_detalle[i] or len(observaciones_detalle[i].strip()) < 5):
                        errores_validacion.append(
                            f'"{detalle_orden.Libros_.titulo}": Debe proporcionar observaciones para productos rechazados (mínimo 5 caracteres)'
                        )
                    
                    # Si el estado es "Dañado" o "Defectuoso", debe haber observaciones
                    if estados_producto[i] in ['Dañado', 'Defectuoso'] and (not observaciones_detalle[i] or len(observaciones_detalle[i].strip()) < 5):
                        errores_validacion.append(
                            f'"{detalle_orden.Libros_.titulo}": Debe proporcionar observaciones para productos {estados_producto[i].lower()}s'
                        )
            
            if errores_validacion:
                for error in errores_validacion:
                    flash(f'❌ {error}', 'error')
                return redirect(url_for('orden_compra.recepcionar', id=id))
            
            # Obtener empleado receptor
            if hasattr(current_user, 'id_empleado'):
                id_empleado_receptor = current_user.id_empleado
            else:
                empleado = db.session.execute(
                    select(Empleados).where(Empleados.activo == 1).limit(1)
                ).scalars().first()
                if not empleado:
                    flash('No hay empleados activos para registrar la recepción', 'error')
                    return redirect(url_for('orden_compra.ver', id=id))
                id_empleado_receptor = empleado.id_empleado
            
            # Crear registro de recepción
            nueva_recepcion = RecepcionCompra(
                id_recepcion=get_next_recepcion_id(),
                id_orden=orden.id_orden,
                id_empleado_receptor=id_empleado_receptor,
                fecha_recepcion=datetime.now(),
                numero_guia=request.form.get('numero_guia', '').strip(),
                estado_recepcion=request.form.get('estado_recepcion', 'Aceptado'),
                observaciones=request.form.get('observaciones_recepcion', '').strip(),
                inventariado=0
            )
            
            db.session.add(nueva_recepcion)
            db.session.flush()
            
            # Procesar cada línea de detalle
            productos_procesados = []
            for i in range(len(detalles_ids)):
                detalle_orden = db.session.get(DetalleOrdenCompra, int(detalles_ids[i]))
                if not detalle_orden:
                    continue
                
                cant_recibida = int(cantidades_recibidas[i]) if cantidades_recibidas[i] else 0
                cant_rechazada = int(cantidades_rechazadas[i]) if cantidades_rechazadas[i] else 0
                
                if cant_recibida == 0 and cant_rechazada == 0:
                    continue
                
                # Crear detalle de recepción
                detalle_recepcion = DetalleRecepcionCompra(
                    id_detalle_recepcion=get_next_detalle_recepcion_id(),
                    id_recepcion=nueva_recepcion.id_recepcion,
                    id_detalle_orden=detalle_orden.id_detalle_orden,
                    cantidad_recibida=cant_recibida,
                    cantidad_rechazada=cant_rechazada,
                    estado_producto=estados_producto[i],
                    observaciones=observaciones_detalle[i] if observaciones_detalle[i] else None
                )
                
                db.session.add(detalle_recepcion)
                
                # Actualizar cantidad recibida en detalle de orden
                detalle_orden.cantidad_recibida += cant_recibida
                
                # Actualizar estado de la línea
                if detalle_orden.cantidad_recibida >= detalle_orden.cantidad_ordenada:
                    detalle_orden.estado_linea = 'Recibido Completo'
                elif detalle_orden.cantidad_recibida > 0:
                    detalle_orden.estado_linea = 'Recibido Parcial'
                
                if cant_rechazada > 0:
                    if cant_recibida == 0:
                        detalle_orden.estado_linea = 'Rechazado'
                    detalle_orden.motivo_rechazo = observaciones_detalle[i]
                
                productos_procesados.append(f"{detalle_orden.Libros_.titulo} ({cant_recibida} recibidos)")
            
            db.session.commit()
            
            # Actualizar estado de la orden
            actualizar_estado_orden(orden.id_orden)
            
            flash(f'✅ Recepción registrada exitosamente', 'success')
            flash(f'📦 Productos procesados: {", ".join(productos_procesados[:3])}{"..." if len(productos_procesados) > 3 else ""}', 'info')
            return redirect(url_for('orden_compra.inventariar_recepcion', id=nueva_recepcion.id_recepcion))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar recepción: {str(e)}', 'error')
            print(f"❌ Error en recepción: {str(e)}")
            traceback.print_exc()
            return redirect(url_for('orden_compra.ver', id=id))
    
    # GET - Mostrar formulario
    try:
        if orden.estado in ['Aprobada', 'En Tránsito']:
            orden.estado = 'En Recepción'
            db.session.commit()
            flash(f'📋 Orden marcada como "En Recepción"', 'info')
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ No se pudo actualizar el estado: {str(e)}")
    
    return render_template('orden_compra/recepcionar.html',
                         orden=orden,
                         estados_recepcion=ESTADOS_RECEPCION,
                         estados_producto=ESTADOS_PRODUCTO)

@bp.route('/recepcion/ver/<int:id>')
@login_required
def ver_recepcion(id):
    """Ver detalles de una recepción específica"""
    recepcion = db.session.get(RecepcionCompra, id)
    
    if not recepcion:
        flash('Recepción no encontrada', 'error')
        return redirect(url_for('orden_compra.listar'))
    
    # Calculate totals for this reception
    total_recibido = sum(d.cantidad_recibida for d in recepcion.Detalle_Recepcion_Compra)
    total_rechazado = sum(d.cantidad_rechazada for d in recepcion.Detalle_Recepcion_Compra)
    
    # Count products by status
    productos_buenos = sum(d.cantidad_recibida for d in recepcion.Detalle_Recepcion_Compra if d.estado_producto == 'Bueno')
    productos_danados = sum(d.cantidad_recibida for d in recepcion.Detalle_Recepcion_Compra if d.estado_producto == 'Dañado')
    productos_defectuosos = sum(d.cantidad_recibida for d in recepcion.Detalle_Recepcion_Compra if d.estado_producto == 'Defectuoso')
    
    return render_template('orden_compra/ver_recepcion.html',
                         recepcion=recepcion,
                         total_recibido=total_recibido,
                         total_rechazado=total_rechazado,
                         productos_buenos=productos_buenos,
                         productos_danados=productos_danados,
                         productos_defectuosos=productos_defectuosos)

@bp.route('/recepcion/inventariar/<int:id>', methods=['GET', 'POST'])
@login_required
def inventariar_recepcion(id):
    """Inventariar productos recepcionados (crear movimientos de inventario)"""
    recepcion = db.session.get(RecepcionCompra, id)
    
    if not recepcion:
        flash('Recepción no encontrada', 'error')
        return redirect(url_for('orden_compra.listar'))
    
    if recepcion.inventariado:
        flash('Esta recepción ya ha sido inventariada', 'warning')
        return redirect(url_for('orden_compra.ver_recepcion', id=id))
    
    if request.method == 'POST':
        try:
            # Get employee
            if hasattr(current_user, 'id_empleado'):
                id_empleado = current_user.id_empleado
            else:
                empleado = db.session.execute(
                    select(Empleados).where(Empleados.activo == 1).limit(1)
                ).scalars().first()
                if not empleado:
                    flash('No hay empleados activos para registrar el inventario', 'error')
                    return redirect(url_for('orden_compra.ver_recepcion', id=id))
                id_empleado = empleado.id_empleado
            
            orden = recepcion.Orden_Compra_
            referencia = f"REC-{recepcion.id_recepcion}"
            
            movimientos_creados = 0
            productos_actualizados = []
            productos_omitidos = []
            
            # Create inventory movements for each received detail
            # FIXED: Only create movements for products in "Bueno" state
            # Damaged/Defective products should not enter inventory
            for detalle_recepcion in recepcion.Detalle_Recepcion_Compra:
                cantidad_a_inventariar = detalle_recepcion.cantidad_recibida
                
                # Only inventory products marked as "Bueno" (Good condition)
                if cantidad_a_inventariar > 0:
                    libro_titulo = detalle_recepcion.Detalle_Orden_Compra_.Libros_.titulo
                    estado = detalle_recepcion.estado_producto
                    
                    if estado == 'Bueno':
                        # Create inventory movement for good products
                        crear_movimiento_inventario(
                            detalle_recepcion.Detalle_Orden_Compra_,
                            cantidad_a_inventariar,
                            orden.id_sucursal,
                            id_empleado,
                            referencia
                        )
                        
                        movimientos_creados += 1
                        productos_actualizados.append(f"{libro_titulo} ({cantidad_a_inventariar})")
                    else:
                        # Products that are Damaged or Defective don't enter inventory
                        productos_omitidos.append(f"{libro_titulo} ({cantidad_a_inventariar} - {estado})")
                        print(f"⚠️ Producto omitido del inventario: {libro_titulo} - Estado: {estado}")
            
            # Mark reception as inventoried
            recepcion.inventariado = 1
            recepcion.fecha_inventariado = datetime.now()
            
            db.session.commit()
            
            # Success messages
            if movimientos_creados > 0:
                flash(f'✅ Recepción inventariada exitosamente', 'success')
                flash(f'📦 {movimientos_creados} movimientos de inventario creados', 'info')
                
                productos_texto = ", ".join(productos_actualizados[:3])
                if len(productos_actualizados) > 3:
                    productos_texto += f" y {len(productos_actualizados) - 3} más"
                flash(f'📚 Productos actualizados: {productos_texto}', 'info')
            
            if productos_omitidos:
                omitidos_texto = ", ".join(productos_omitidos[:3])
                if len(productos_omitidos) > 3:
                    omitidos_texto += f" y {len(productos_omitidos) - 3} más"
                flash(f'⚠️ Productos NO ingresados al inventario (Dañados/Defectuosos): {omitidos_texto}', 'warning')
            
            if movimientos_creados == 0:
                flash('⚠️ No se crearon movimientos de inventario. Todos los productos recibidos están dañados o defectuosos.', 'warning')
            
            # Redirect to inventory to verify
            return redirect(url_for('inventarios.listar', busqueda=referencia))
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al inventariar: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'Error al inventariar productos: {str(e)}', 'error')
            return redirect(url_for('orden_compra.ver_recepcion', id=id))
    
    # GET - Show confirmation
    # Calculate how many products will actually be inventoried
    productos_buenos = sum(
        d.cantidad_recibida for d in recepcion.Detalle_Recepcion_Compra 
        if d.estado_producto == 'Bueno' and d.cantidad_recibida > 0
    )
    productos_malos = sum(
        d.cantidad_recibida for d in recepcion.Detalle_Recepcion_Compra 
        if d.estado_producto != 'Bueno' and d.cantidad_recibida > 0
    )
    
    return render_template('orden_compra/inventariar.html', 
                         recepcion=recepcion,
                         productos_buenos=productos_buenos,
                         productos_malos=productos_malos)

# ================== API ENDPOINTS ==================

@bp.route('/api/libros-editorial/<int:editorial_id>')
@login_required
def api_libros_editorial(editorial_id):
    """API: Obtener libros de una editorial específica"""
    try:
        # Buscar libros relacionados con esta editorial usando LibroEditoriales
        libros = db.session.query(Libros).join(
            LibroEditoriales,
            Libros.id_libro == LibroEditoriales.id_libro
        ).filter(
            LibroEditoriales.id_editorial == editorial_id
        ).order_by(Libros.titulo).all()
        
        return jsonify([{
            'id_libro': libro.id_libro,
            'titulo': libro.titulo,
            'isbn': libro.isbn,
            'stock_fisico': libro.stock_fisico,
            'stock_digital': libro.stock_digital,
            'precio_venta': float(libro.precio_venta)
        } for libro in libros])
        
    except Exception as e:
        print(f"Error in api_libros_editorial: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@bp.route('/api/precio-compra/<int:libro_id>/<int:editorial_id>')
@login_required
def api_precio_compra(libro_id, editorial_id):
    """API: Obtener precio de compra de un libro para una editorial"""
    try:
        print(f"🔍 Getting price for libro_id={libro_id}, editorial_id={editorial_id}")
        precio = obtener_precio_compra(libro_id, editorial_id)
        print(f"💰 Found price: {precio}")
        
        libro = db.session.get(Libros, libro_id)
        precio_venta = float(libro.precio_venta) if libro else 0
        
        # Verificar si tiene precio personalizado configurado
        tiene_precio_personalizado = db.session.execute(
            select(PrecioCompraEditorial)
            .where(
                and_(
                    PrecioCompraEditorial.id_libro == libro_id,
                    PrecioCompraEditorial.id_editorial == editorial_id,
                    PrecioCompraEditorial.activo == 1
                )
            )
        ).scalars().first() is not None
        
        # Si no hay precio configurado, retornar 0
        precio_compra = float(precio) if precio is not None else 0.0
        
        print(f"✅ Returning precio_compra={precio_compra}, tiene_precio={tiene_precio_personalizado}")
        
        return jsonify({
            'precio_compra': precio_compra,
            'precio_venta': precio_venta,
            'tiene_precio_personalizado': tiene_precio_personalizado
        })
        
    except Exception as e:
        print(f"Error in api_precio_compra: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@bp.route('/api/detalle-orden/<int:orden_id>')
@login_required
def api_detalle_orden(orden_id):
    """API: Obtener detalles de una orden"""
    try:
        detalles = db.session.execute(
            select(DetalleOrdenCompra)
            .where(DetalleOrdenCompra.id_orden == orden_id)
        ).scalars().all()
        
        return jsonify([{
            'id_detalle': d.id_detalle_orden,
            'libro': d.Libros_.titulo,
            'cantidad_ordenada': d.cantidad_ordenada,
            'cantidad_recibida': d.cantidad_recibida,
            'precio_unitario': float(d.precio_unitario),
            'subtotal': float(d.subtotal),
            'formato': d.formato,
            'estado': d.estado_linea
        } for d in detalles])
        
    except Exception as e:
        print(f"Error in api_detalle_orden: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500