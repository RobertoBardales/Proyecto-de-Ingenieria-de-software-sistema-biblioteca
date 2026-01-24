from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_, and_
from models import (
    Venta, DetalleVenta, Libros, Clientes, Empleados, MetodoDePago, 
    EstadoVenta, Inventarios, Sucursales, Autores, LibroAutores, FacturasSar
)
from app import db
from datetime import datetime, time
from decimal import Decimal
from app.routes.sar import get_parametro_sar_activo, generar_numero_factura_sar, validar_sar_para_venta
from app.utils.email_service import send_invoice_email, send_payment_confirmation_email
from app.utils.notification_service import (
    notificar_venta_completada,
    notificar_venta_pendiente,
    notificar_pago_confirmado
)

bp = Blueprint('ventas', __name__, url_prefix='/ventas')

# ================== CONFIGURACIÓN ==================

DESCUENTO_MAXIMO_PORCENTAJE = Decimal('20.0')  # 20% máximo
DESCUENTO_MAXIMO_ABSOLUTO = Decimal('10000.0')  # L. 10,000 máximo

# ================== FUNCIONES AUXILIARES ==================

def get_sucursal_por_cliente(cliente_id):
    """
    Obtiene la sucursal asignada directamente al cliente
    
    Retorna: id_sucursal o None si no tiene asignada
    """
    try:
        cliente = db.session.get(Clientes, cliente_id)
        
        if not cliente:
            return None
        
        # Si el cliente tiene sucursal asignada y está activa
        if cliente.id_sucursal:
            sucursal = db.session.get(Sucursales, cliente.id_sucursal)
            if sucursal and sucursal.activo:
                return cliente.id_sucursal
        
        # Fallback: primera sucursal activa si el cliente no tiene asignada
        sucursal_activa = db.session.execute(
            select(Sucursales).where(Sucursales.activo == 1).limit(1)
        ).scalars().first()
        
        return sucursal_activa.id_sucursal if sucursal_activa else None
                
    except Exception as e:
        print(f"Error al obtener sucursal del cliente: {str(e)}")
        return None

def get_next_venta_id():
    """Obtiene el siguiente ID disponible para Venta"""
    max_id = db.session.execute(
        select(func.max(Venta.id_venta))
    ).scalar()
    return (max_id or 0) + 1

def get_next_detalle_venta_id():
    """Obtiene el siguiente ID disponible para DetalleVenta"""
    max_id = db.session.execute(
        select(func.max(DetalleVenta.id_detalle))
    ).scalar()
    return (max_id or 0) + 1

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

def generar_numero_factura_simple(sucursal_id):
    """
    Genera número de factura simple sin SAR
    Formato: FAC-YYYYMMDD-####
    """
    fecha = datetime.now().strftime('%Y%m%d')
    today_start = datetime.combine(datetime.now().date(), time.min)
    today_end = datetime.combine(datetime.now().date(), time.max)
    
    count = db.session.execute(
        select(func.count(Venta.id_venta))
        .where(
            and_(
                Venta.fecha_venta >= today_start,
                Venta.fecha_venta <= today_end
            )
        )
    ).scalar() or 0
    
    return f"FAC-{fecha}-{count + 1:04d}"

def generar_y_asignar_factura(venta, sucursal_id):
    """
    Genera número de factura basado en la sucursal seleccionada.
    Busca el SAR activo de esa sucursal y lo usa.
    
    Retorna: (numero_factura, id_parametro_sar o None)
    """
    # Buscar SAR activo para la sucursal seleccionada
    parametro_sar = get_parametro_sar_activo(sucursal_id)
    
    if parametro_sar:
        try:
            # Generar número usando el SAR de la sucursal
            numero_factura = generar_numero_factura_sar(parametro_sar)
            
            # Actualizar última factura
            parametro_sar.ultima_factura = numero_factura
            
            # Retornar número y el ID del parámetro SAR usado
            return numero_factura, parametro_sar.id_parametro
            
        except ValueError as e:
            # Rango agotado o error
            flash(f'⚠️ Advertencia SAR: {str(e)}. Usando numeración simple.', 'warning')
            return generar_numero_factura_simple(sucursal_id), None
    else:
        # No hay SAR configurado para esta sucursal
        return generar_numero_factura_simple(sucursal_id), None


def validar_descuento_porcentaje(porcentaje, subtotal):
    """
    Valida que el porcentaje de descuento no exceda los límites configurados
    Retorna: (es_valido, mensaje_error, descuento_calculado)
    """
    if porcentaje < 0:
        return False, "El descuento no puede ser negativo", Decimal(0)
    
    # Validar porcentaje máximo
    if porcentaje > DESCUENTO_MAXIMO_PORCENTAJE:
        return False, f"El descuento no puede exceder el {DESCUENTO_MAXIMO_PORCENTAJE}%", Decimal(0)
    
    # Calcular descuento en monto
    descuento = (subtotal * porcentaje) / Decimal(100)
    
    # Validar que no exceda el máximo absoluto
    if descuento > DESCUENTO_MAXIMO_ABSOLUTO:
        return False, f"El descuento calculado excede el máximo permitido de L. {DESCUENTO_MAXIMO_ABSOLUTO:,.2f}", Decimal(0)
    
    # Validar que no exceda el subtotal
    if descuento > subtotal:
        return False, "El descuento no puede exceder el subtotal", Decimal(0)
    
    return True, "", descuento

def calcular_isv(subtotal, porcentaje=15):
    """Calcula ISV (Impuesto Sobre Ventas)"""
    return Decimal(subtotal) * Decimal(porcentaje) / Decimal(100)

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
        formato='Físico',
        fecha_movimiento=datetime.now(),
        id_empleado=empleado_id,
        motivo=motivo,
        observaciones=observaciones,
        referencia=referencia
    )
    
    db.session.add(movimiento)
    return movimiento

def registrar_venta_inventario(libro, cantidad, empleado_id, venta_id, formato='Físico', sucursal_id=None):
    """Registra movimiento de inventario por venta"""
    if formato == 'Físico':
        stock_anterior = libro.stock_fisico
        libro.stock_fisico -= cantidad
        stock_nuevo = libro.stock_fisico
    else:  # Digital
        stock_anterior = libro.stock_digital
        libro.stock_digital -= cantidad
        stock_nuevo = libro.stock_digital
    
    # Si no se proporciona sucursal_id, usar la principal
    if sucursal_id is None:
        sucursal_id = get_sucursal_principal()
    
    crear_movimiento_inventario(
        libro_id=libro.id_libro,
        sucursal_id=sucursal_id,
        tipo_movimiento='Venta',
        cantidad=cantidad,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        empleado_id=empleado_id,
        motivo=f'Venta de libro a cliente',
        referencia=f'VENTA-{venta_id}',
        observaciones=f'Salida automática por venta #{venta_id} - Formato: {formato}'
    )

# ================== CARRITO DE COMPRAS ==================

@bp.route('/carrito')
@login_required
def carrito():
    """Ver carrito de compras"""
    cart_items = session.get(f'cart_{current_user.id_cliente}', {})
    
    if not cart_items:
        return render_template('ventas/carrito.html', items=[], subtotal=0, isv=0, total=0)
    
    items = []
    subtotal = Decimal(0)
    
    for libro_id, item_data in cart_items.items():
        libro = db.session.get(Libros, int(libro_id))
        if libro:
            cantidad = item_data['cantidad']
            formato = item_data.get('formato', 'Físico')
            precio = libro.precio_venta
            item_subtotal = precio * cantidad
            
            items.append({
                'libro': libro,
                'cantidad': cantidad,
                'formato': formato,
                'precio': precio,
                'subtotal': item_subtotal
            })
            subtotal += item_subtotal
    
    isv_15 = calcular_isv(subtotal, 15)
    total = subtotal + isv_15
    
    return render_template('ventas/carrito.html', 
                         items=items,
                         subtotal=subtotal,
                         isv=isv_15,
                         total=total)



@bp.route('/carrito/agregar/<int:libro_id>', methods=['POST'])
@login_required
def agregar_al_carrito(libro_id):
    """Agregar libro al carrito"""
    try:
        libro = db.session.get(Libros, libro_id)
        
        if not libro:
            return jsonify({'success': False, 'error': 'Libro no encontrado'}), 404
        
        if not libro.disp_venta:
            return jsonify({'success': False, 'error': 'Libro no disponible para venta'}), 400
        
        cantidad = int(request.form.get('cantidad', 1))
        formato = request.form.get('formato', 'Físico')
        
        # Check stock
        if formato == 'Físico' and libro.stock_fisico < cantidad:
            return jsonify({'success': False, 'error': 'Stock insuficiente'}), 400
        
        if formato == 'Digital' and libro.stock_digital < cantidad:
            return jsonify({'success': False, 'error': 'Stock digital insuficiente'}), 400
        
        cart = session.get(f'cart_{current_user.id_cliente}', {})
        libro_id_str = str(libro_id)
        
        if libro_id_str in cart:
            cart[libro_id_str]['cantidad'] += cantidad
        else:
            cart[libro_id_str] = {
                'cantidad': cantidad,
                'formato': formato
            }
        
        session[f'cart_{current_user.id_cliente}'] = cart
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': f'"{libro.titulo}" agregado al carrito',
            'cart_count': len(cart)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/carrito/actualizar/<int:libro_id>', methods=['POST'])
@login_required
def actualizar_carrito(libro_id):
    """Actualizar cantidad en carrito"""
    try:
        cantidad = int(request.form.get('cantidad', 1))
        
        if cantidad <= 0:
            return eliminar_del_carrito(libro_id)
        
        libro = db.session.get(Libros, libro_id)
        cart = session.get(f'cart_{current_user.id_cliente}', {})
        libro_id_str = str(libro_id)
        
        if libro_id_str in cart:
            formato = cart[libro_id_str]['formato']
            
            # Check stock
            if formato == 'Físico' and libro.stock_fisico < cantidad:
                return jsonify({'success': False, 'error': 'Stock insuficiente'}), 400
            
            if formato == 'Digital' and libro.stock_digital < cantidad:
                return jsonify({'success': False, 'error': 'Stock digital insuficiente'}), 400
            
            cart[libro_id_str]['cantidad'] = cantidad
            session[f'cart_{current_user.id_cliente}'] = cart
            session.modified = True
            
            return jsonify({'success': True, 'message': 'Carrito actualizado'})
        
        return jsonify({'success': False, 'error': 'Libro no encontrado en carrito'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/carrito/eliminar/<int:libro_id>', methods=['POST'])
@login_required
def eliminar_del_carrito(libro_id):
    """Eliminar libro del carrito"""
    try:
        cart = session.get(f'cart_{current_user.id_cliente}', {})
        libro_id_str = str(libro_id)
        
        if libro_id_str in cart:
            del cart[libro_id_str]
            session[f'cart_{current_user.id_cliente}'] = cart
            session.modified = True
            
            return jsonify({
                'success': True,
                'message': 'Libro eliminado del carrito',
                'cart_count': len(cart)
            })
        
        return jsonify({'success': False, 'error': 'Libro no encontrado en carrito'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/carrito/vaciar', methods=['POST'])
@login_required
def vaciar_carrito():
    """Vaciar carrito completo"""
    session[f'cart_{current_user.id_cliente}'] = {}
    session.modified = True
    return jsonify({'success': True, 'message': 'Carrito vaciado'})

@bp.route('/carrito/count')
@login_required
def carrito_count():
    """Obtener cantidad de items en el carrito"""
    cart = session.get(f'cart_{current_user.id_cliente}', {})
    return jsonify({'count': len(cart)})

# ================== CHECKOUT ==================

@bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Procesar checkout y crear venta"""
    
    if request.method == 'GET':
        cart_items = session.get(f'cart_{current_user.id_cliente}', {})
        
        if not cart_items:
            flash('El carrito está vacío', 'warning')
            return redirect(url_for('ventas.carrito'))
        
        # Get client info
        cliente = db.session.get(Clientes, current_user.id_cliente)
        
        # Determinar sucursal automáticamente basado en ID del cliente
        sucursal_id = get_sucursal_por_cliente(cliente.id_cliente)
        
        if not sucursal_id:
            flash('⚠️ No hay sucursales activas disponibles. Contacta al administrador.', 'error')
            return redirect(url_for('ventas.carrito'))
        
        sucursal = db.session.get(Sucursales, sucursal_id)
        
        # ============ VALIDATE SAR ============
        es_valido, mensaje_error, parametro_sar = validar_sar_para_venta(sucursal_id)
        
        if not es_valido:
            flash(f'❌ No se puede procesar la compra: {mensaje_error}', 'error')
            sar_error = mensaje_error
        else:
            sar_error = None
            
            # Optional: Show warning if running low on invoices
            if parametro_sar and parametro_sar.ultima_factura:
                correlativo_actual = int(parametro_sar.ultima_factura.split('-')[-1])
                rango_final_num = int(parametro_sar.rango_final.split('-')[-1])
                facturas_restantes = rango_final_num - correlativo_actual
                
                if facturas_restantes < 100:
                    flash(f'⚠️ Advertencia: Solo quedan {facturas_restantes} facturas disponibles en el rango SAR', 'warning')
        # =======================================
        
        # Calculate totals
        items = []
        subtotal = Decimal(0)
        
        for libro_id, item_data in cart_items.items():
            libro = db.session.get(Libros, int(libro_id))
            if libro:
                cantidad = item_data['cantidad']
                formato = item_data.get('formato', 'Físico')
                precio = libro.precio_venta
                item_subtotal = precio * cantidad
                
                # Get authors for display
                autores = db.session.execute(
                    select(Autores)
                    .join(LibroAutores)
                    .where(LibroAutores.id_libro == libro.id_libro)
                ).scalars().all()
                
                items.append({
                    'libro': libro,
                    'autores': autores,
                    'cantidad': cantidad,
                    'formato': formato,
                    'precio': precio,
                    'subtotal': item_subtotal
                })
                subtotal += item_subtotal
        
        isv_15 = calcular_isv(subtotal, 15)
        total = subtotal + isv_15
        
        # Get payment methods
        metodos_pago = db.session.execute(
            select(MetodoDePago).where(MetodoDePago.activo == 1).order_by(MetodoDePago.nombre)
        ).scalars().all()
        
        return render_template('ventas/checkout.html',
                             items=items,
                             subtotal=subtotal,
                             isv=isv_15,
                             total=total,
                             metodos_pago=metodos_pago,
                             sucursal=sucursal,
                             cliente=cliente,
                             descuento_maximo_porcentaje=DESCUENTO_MAXIMO_PORCENTAJE,
                             descuento_maximo_absoluto=DESCUENTO_MAXIMO_ABSOLUTO,
                             sar_error=sar_error)
    
    # POST - Process sale
    try:
        cart_items = session.get(f'cart_{current_user.id_cliente}', {})
        
        if not cart_items:
            flash('El carrito está vacío', 'error')
            return redirect(url_for('ventas.carrito'))
        
        # Get form data
        id_metodo_pago = int(request.form.get('metodo_pago'))
        metodo_pago = db.session.get(MetodoDePago, id_metodo_pago)
        exonerado = 1 if request.form.get('exonerado') else 0
        numero_reg_exoneracion = request.form.get('numero_reg_exoneracion', '').strip() or ''
        numero_reg_sag = request.form.get('numero_reg_sag', '').strip() or ''
        descuento_input = Decimal(request.form.get('descuento', 0))

        # Capturar datos de método mixto
        tarjeta_ultimos4 = None
        monto_efectivo = None

        if metodo_pago and 'mixto' in metodo_pago.nombre.lower():
            tarjeta_ultimos4 = request.form.get('tarjeta_ultimos4', '').strip()
            monto_efectivo_str = request.form.get('monto_efectivo', '0').strip()
            
            if not tarjeta_ultimos4 or len(tarjeta_ultimos4) != 4:
                flash('Debes ingresar los últimos 4 dígitos de la tarjeta para pago mixto', 'error')
                return redirect(url_for('ventas.checkout'))
            
            try:
                monto_efectivo = Decimal(monto_efectivo_str)
                if monto_efectivo <= 0:
                    flash('El monto en efectivo debe ser mayor a cero', 'error')
                    return redirect(url_for('ventas.checkout'))
            except:
                flash('Monto en efectivo inválido', 'error')
                return redirect(url_for('ventas.checkout'))

        
        # Get cliente_id
        if current_user.tipo_usuario != 'cliente':
            flash('Solo los clientes pueden realizar compras', 'error')
            return redirect(url_for('ventas.carrito'))
        
        cliente_id = current_user.id_cliente
        
        # Determinar sucursal automáticamente (NO desde el formulario)
        id_sucursal = get_sucursal_por_cliente(cliente_id)
        
        if not id_sucursal:
            flash('No hay sucursales activas disponibles', 'error')
            return redirect(url_for('ventas.carrito'))
        
        # ============ VALIDATE SAR BEFORE PROCEEDING ============
        es_valido, mensaje_error, parametro_sar = validar_sar_para_venta(id_sucursal)
        
        if not es_valido:
            flash(f'❌ No se puede procesar la compra: {mensaje_error}', 'error')
            return redirect(url_for('ventas.checkout'))
        # ========================================================
        
        # Validar que la sucursal existe y está activa
        sucursal = db.session.get(Sucursales, id_sucursal)
        if not sucursal or not sucursal.activo:
            flash('Error con la sucursal asignada. Contacta al administrador.', 'error')
            return redirect(url_for('ventas.checkout'))
        
        # Get empleado (or use default if client checkout)
        empleado = db.session.execute(
            select(Empleados).where(Empleados.activo == 1).limit(1)
        ).scalars().first()
        
        if not empleado:
            flash('No hay empleados disponibles para procesar la venta', 'error')
            return redirect(url_for('ventas.carrito'))
        
        # Get payment method to determine initial status
        metodo_pago = db.session.get(MetodoDePago, id_metodo_pago)
        if not metodo_pago:
            flash('Método de pago inválido', 'error')
            return redirect(url_for('ventas.checkout'))
        
        # Calculate totals and collect items
        subtotal = Decimal(0)
        items_to_sell = []
        
        for libro_id, item_data in cart_items.items():
            libro = db.session.get(Libros, int(libro_id))
            if not libro:
                flash(f'Libro con ID {libro_id} no encontrado', 'error')
                return redirect(url_for('ventas.carrito'))
            
            cantidad = item_data['cantidad']
            formato = item_data.get('formato', 'Físico')
            
            # Verify stock
            if formato == 'Físico' and libro.stock_fisico < cantidad:
                flash(f'Stock insuficiente para "{libro.titulo}"', 'error')
                return redirect(url_for('ventas.carrito'))
            
            if formato == 'Digital' and libro.stock_digital < cantidad:
                flash(f'Stock digital insuficiente para "{libro.titulo}"', 'error')
                return redirect(url_for('ventas.carrito'))
            
            precio = libro.precio_venta
            item_subtotal = precio * cantidad
            subtotal += item_subtotal
            
            items_to_sell.append({
                'libro': libro,
                'cantidad': cantidad,
                'formato': formato,
                'precio': precio,
                'subtotal': item_subtotal
            })
        
        # Validate discount - using percentage validation
        descuento_porcentaje = Decimal(request.form.get('discount_percentage', 0))

        if descuento_porcentaje > 0:
            es_valido, mensaje_error, descuento = validar_descuento_porcentaje(descuento_porcentaje, subtotal)
            if not es_valido:
                flash(f'Error en descuento: {mensaje_error}', 'error')
                return redirect(url_for('ventas.checkout'))
        else:
            descuento = Decimal(0)
        
        # Calculate taxes
        if exonerado:
            isv_15 = Decimal(0)
            isv_18 = Decimal(0)
            importe_exonerado = subtotal
        else:
            isv_15 = calcular_isv(subtotal - descuento, 15)
            isv_18 = Decimal(0)
            importe_exonerado = Decimal(0)
        
        total = subtotal + isv_15 + isv_18 - descuento
        
        # Determine initial estado based on payment method
        if 'transferencia' in metodo_pago.nombre.lower() or 'depósito' in metodo_pago.nombre.lower():
            id_estado_inicial = 2  # Pendiente de Pago
        else:
            id_estado_inicial = 1  # Completada
        
        # Verify the estado exists
        estado_venta = db.session.get(EstadoVenta, id_estado_inicial)
        if not estado_venta:
            estado_venta = db.session.execute(
                select(EstadoVenta).where(EstadoVenta.activo == 1).limit(1)
            ).scalars().first()
            
            if not estado_venta:
                flash('No hay estados de venta configurados. Contacte al administrador.', 'error')
                return redirect(url_for('ventas.carrito'))
            
            id_estado_inicial = estado_venta.id_estado
        
        # Create sale WITHOUT invoice number (will be generated after flush)
        nueva_venta = Venta(
            id_venta=get_next_venta_id(),
            id_cliente=cliente_id,
            id_empleado=empleado.id_empleado,
            id_metodo_pago=id_metodo_pago,
            id_estado=id_estado_inicial,
            fecha_venta=datetime.now(),
            subtotal=subtotal,
            isv_15=isv_15,
            isv_18=isv_18,
            descuento=descuento,
            total=total,
            exonerado=exonerado,
            numero_factura='TEMPORAL',
            importe_exonerado=importe_exonerado,
            numero_reg_exoneracion=numero_reg_exoneracion,
            numero_reg_sag=numero_reg_sag,
            metodo_mixto_tarjeta_ultimos4=tarjeta_ultimos4,
            metodo_mixto_efectivo=monto_efectivo
        )

        db.session.add(nueva_venta)
        db.session.flush()

        # Create sale details and update inventory
        for item in items_to_sell:
            detalle = DetalleVenta(
                id_detalle=get_next_detalle_venta_id(),
                id_venta=nueva_venta.id_venta,
                id_libro=item['libro'].id_libro,
                cantidad=item['cantidad'],
                precio_unitario=item['precio'],
                subtotal=item['subtotal']
            )
            
            db.session.add(detalle)
            
            # Register inventory movement con la sucursal asignada
            registrar_venta_inventario(
                item['libro'], 
                item['cantidad'], 
                empleado.id_empleado, 
                nueva_venta.id_venta,
                item['formato'],
                id_sucursal
            )

        # Generate invoice number using assigned sucursal
        numero_factura, id_parametro_sar = generar_y_asignar_factura(nueva_venta, id_sucursal)
        nueva_venta.numero_factura = numero_factura
        nueva_venta.id_parametro_sar = id_parametro_sar
        
        # Commit everything
        db.session.commit()
        
        # Get cliente for notifications
        cliente = db.session.get(Clientes, cliente_id)
        
        # Clear cart
        session[f'cart_{current_user.id_cliente}'] = {}
        session.modified = True
        
        # Send notifications and emails
        try:
            # Create notification
            if id_estado_inicial == 2:
                notificar_venta_pendiente(nueva_venta, cliente)
            else:
                notificar_venta_completada(nueva_venta, cliente)
            
            # Get details for email
            detalles = db.session.execute(
                select(DetalleVenta, Libros)
                .join(Libros, DetalleVenta.id_libro == Libros.id_libro)
                .where(DetalleVenta.id_venta == nueva_venta.id_venta)
            ).all()
            
            # Get SAR info
            factura_sar = None
            if id_parametro_sar:
                factura_sar = db.session.get(FacturasSar, id_parametro_sar)
            
            # Send invoice email
            send_invoice_email(
                venta=nueva_venta,
                cliente=cliente,
                detalles=detalles,
                factura_sar=factura_sar,
                sucursal=sucursal
            )
        except Exception as e:
            print(f"Error sending notifications/emails: {str(e)}")
            # Don't fail the sale if notification fails
        
        # Success message
        if id_estado_inicial == 2:
            flash(f'✅ Venta #{nueva_venta.id_venta} registrada en {sucursal.nombre}. Factura: {numero_factura}. Te enviamos un email con los detalles. Pendiente de confirmación de pago.', 'info')
        else:
            flash(f'✅ Venta #{nueva_venta.id_venta} completada en {sucursal.nombre}. Factura: {numero_factura}. Revisa tu email para la factura.', 'success')
        
        return redirect(url_for('ventas.ver', id=nueva_venta.id_venta))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error detallado: {str(e)}")
        flash(f'Error al procesar venta: {str(e)}', 'error')
        return redirect(url_for('ventas.checkout'))
# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todas las ventas"""
    estado = request.args.get('estado', '')
    cliente_id = request.args.get('cliente', '')
    fecha_desde = request.args.get('fecha_desde', '')
    fecha_hasta = request.args.get('fecha_hasta', '')
    
    query = db.session.query(Venta, Clientes, Empleados, MetodoDePago, EstadoVenta).join(
        Clientes, Venta.id_cliente == Clientes.id_cliente
    ).join(
        Empleados, Venta.id_empleado == Empleados.id_empleado
    ).join(
        MetodoDePago, Venta.id_metodo_pago == MetodoDePago.id_metodo_pago
    ).join(
        EstadoVenta, Venta.id_estado == EstadoVenta.id_estado
    )
# Filter by user type
    if current_user.tipo_usuario == 'cliente':
        query = query.filter(Venta.id_cliente == current_user.id_cliente)

    # Apply filters
    if estado:
        query = query.filter(Venta.id_estado == int(estado))

    if cliente_id and current_user.tipo_usuario in ['admin', 'empleado']:
        query = query.filter(Venta.id_cliente == int(cliente_id))

    if fecha_desde:
        query = query.filter(Venta.fecha_venta >= datetime.strptime(fecha_desde, '%Y-%m-%d'))

    if fecha_hasta:
        query = query.filter(Venta.fecha_venta <= datetime.strptime(fecha_hasta, '%Y-%m-%d'))

    query = query.order_by(Venta.fecha_venta.desc())

    ventas = query.all()

    # Get item counts for each sale
    ventas_data = []
    for venta, cliente, empleado, metodo_pago, estado_venta in ventas:
        items_count = db.session.execute(
            select(func.count(DetalleVenta.id_detalle))
            .where(DetalleVenta.id_venta == venta.id_venta)
        ).scalar() or 0
        
        ventas_data.append({
            'venta': venta,
            'cliente': cliente,
            'empleado': empleado,
            'metodo_pago': metodo_pago,
            'estado': estado_venta,
            'items_count': items_count
        })

    # Get data for filters
    clientes = []
    if current_user.tipo_usuario in ['admin', 'empleado']:
        clientes = db.session.execute(
            select(Clientes).order_by(Clientes.apellidos, Clientes.nombres)
        ).scalars().all()

    estados = db.session.execute(
        select(EstadoVenta).order_by(EstadoVenta.nombre)
    ).scalars().all()

    return render_template('ventas/listar.html',
                         ventas_data=ventas_data,
                         clientes=clientes,
                         estados=estados,
                         estado_actual=estado,
                         cliente_actual=cliente_id,
                         fecha_desde_actual=fecha_desde,
                         fecha_hasta_actual=fecha_hasta)

@bp.route('/confirmar-pago/<int:id>', methods=['POST'])
@login_required
def confirmar_pago(id):
    """Confirmar pago de venta pendiente"""
    try:
        venta = db.session.get(Venta, id)
        
        if not venta:
            flash('Venta no encontrada', 'error')
            return redirect(url_for('ventas.listar'))
        
        if venta.id_estado == 1:
            flash('Esta venta ya está completada', 'info')
            return redirect(url_for('ventas.ver', id=id))
        
        if venta.id_estado == 3:
            flash('Esta venta está cancelada', 'warning')
            return redirect(url_for('ventas.ver', id=id))
        
        if venta.id_estado != 2:  # Not pending payment
            flash('Esta venta no está pendiente de pago', 'warning')
            return redirect(url_for('ventas.ver', id=id))
        
        # Update to completed
        venta.id_estado = 1  # Completada
        db.session.commit()

        cliente = db.session.get(Clientes, venta.id_cliente)
        
        # Send only notification (not email)
        try:
            notificar_pago_confirmado(venta, cliente)
        except Exception as e:
            print(f"Error sending notification: {str(e)}")
        
        flash('✅ Pago confirmado exitosamente. Venta completada.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al confirmar pago: {str(e)}', 'error')

    return redirect(url_for('ventas.ver', id=id))

@bp.route('/enviar-email/<int:id>', methods=['POST'])
@login_required
def enviar_factura_email(id):
    """Manually send invoice via email"""
    try:
        resultado = db.session.execute(
            select(Venta, Clientes)
            .join(Clientes, Venta.id_cliente == Clientes.id_cliente)
            .where(Venta.id_venta == id)
        ).first()
        
        if not resultado:
            flash('Venta no encontrada', 'error')
            return redirect(url_for('ventas.listar'))
        
        venta, cliente = resultado
        
        # Check permissions
        if current_user.tipo_usuario == 'cliente' and venta.id_cliente != current_user.id_cliente:
            flash('No tienes permisos para esta acción', 'error')
            return redirect(url_for('ventas.listar'))
        
        # Get details
        detalles = db.session.execute(
            select(DetalleVenta, Libros)
            .join(Libros, DetalleVenta.id_libro == Libros.id_libro)
            .where(DetalleVenta.id_venta == id)
        ).all()
        
        # Get SAR and sucursal
        factura_sar = None
        sucursal = None
        
        if venta.id_parametro_sar:
            factura_sar = db.session.get(FacturasSar, venta.id_parametro_sar)
            if factura_sar:
                sucursal = db.session.get(Sucursales, factura_sar.id_sucursal)
        
        if not sucursal:
            sucursal = db.session.get(Sucursales, get_sucursal_principal())
        
        # Send email
        success = send_invoice_email(venta, cliente, detalles, factura_sar, sucursal)
        
        if success:
            flash(f'✅ Factura enviada exitosamente a {cliente.email}', 'success')
        else:
            flash('❌ Error al enviar el email. Intenta nuevamente.', 'error')
        
    except Exception as e:
        flash(f'Error al enviar email: {str(e)}', 'error')

    return redirect(url_for('ventas.ver', id=id))

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalles de una venta"""
    resultado = db.session.execute(
        select(Venta, Clientes, Empleados, MetodoDePago, EstadoVenta)
        .join(Clientes, Venta.id_cliente == Clientes.id_cliente)
        .join(Empleados, Venta.id_empleado == Empleados.id_empleado)
        .join(MetodoDePago, Venta.id_metodo_pago == MetodoDePago.id_metodo_pago)
        .join(EstadoVenta, Venta.id_estado == EstadoVenta.id_estado)
        .where(Venta.id_venta == id)
    ).first()
    
    if not resultado:
        flash('Venta no encontrada', 'error')
        return redirect(url_for('ventas.listar'))

    venta, cliente, empleado, metodo_pago, estado = resultado

    # Check permissions
    if current_user.tipo_usuario == 'cliente' and venta.id_cliente != current_user.id_cliente:
        flash('No tienes permisos para ver esta venta', 'error')
        return redirect(url_for('ventas.listar'))

    # Get sale details
    detalles = db.session.execute(
        select(DetalleVenta, Libros)
        .join(Libros, DetalleVenta.id_libro == Libros.id_libro)
        .where(DetalleVenta.id_venta == id)
    ).all()

    # Get SAR parameter directly from venta.id_parametro_sar
    factura_sar = None
    if venta.id_parametro_sar:
        factura_sar = db.session.get(FacturasSar, venta.id_parametro_sar)

    return render_template('ventas/ver.html',
                         venta=venta,
                         cliente=cliente,
                         empleado=empleado,
                         metodo_pago=metodo_pago,
                         estado=estado,
                         detalles=detalles,
                         factura_sar=factura_sar)

@bp.route('/factura/<int:id>')
@login_required
def factura(id):
    """Generar factura en PDF o vista de impresión"""
    resultado = db.session.execute(
        select(Venta, Clientes, Empleados, MetodoDePago)
        .join(Clientes, Venta.id_cliente == Clientes.id_cliente)
        .join(Empleados, Venta.id_empleado == Empleados.id_empleado)
        .join(MetodoDePago, Venta.id_metodo_pago == MetodoDePago.id_metodo_pago)
        .where(Venta.id_venta == id)
    ).first()
    
    if not resultado:
        flash('Venta no encontrada', 'error')
        return redirect(url_for('ventas.listar'))

    venta, cliente, empleado, metodo_pago = resultado

    # Check permissions
    if current_user.tipo_usuario == 'cliente' and venta.id_cliente != current_user.id_cliente:
        flash('No tienes permisos para ver esta factura', 'error')
        return redirect(url_for('ventas.listar'))

    # Get sale details
    detalles = db.session.execute(
        select(DetalleVenta, Libros)
        .join(Libros, DetalleVenta.id_libro == Libros.id_libro)
        .where(DetalleVenta.id_venta == id)
    ).all()

    # Get SAR and sucursal from venta.id_parametro_sar
    factura_sar = None
    sucursal = None

    if venta.id_parametro_sar:
        factura_sar = db.session.get(FacturasSar, venta.id_parametro_sar)
        if factura_sar:
            sucursal = db.session.get(Sucursales, factura_sar.id_sucursal)

    # Fallback to principal sucursal if no SAR
    if not sucursal:
        sucursal = db.session.get(Sucursales, get_sucursal_principal())

    # Get mask_rtn parameter from query string
    mask_rtn = request.args.get('mask_rtn', '0') == '1'

    return render_template('ventas/factura.html',
                         venta=venta,
                         cliente=cliente,
                         empleado=empleado,
                         metodo_pago=metodo_pago,
                         detalles=detalles,
                         factura_sar=factura_sar,
                         sucursal=sucursal,
                         mask_rtn=mask_rtn)

@bp.route('/cancelar/<int:id>', methods=['POST'])
@login_required
def cancelar(id):
    """Cancelar venta y revertir inventario"""
    if current_user.tipo_usuario not in ['admin', 'empleado']:
        flash('No tienes permisos para cancelar ventas', 'error')
        return redirect(url_for('ventas.ver', id=id))
    
    try:
        venta = db.session.get(Venta, id)
        
        if not venta:
            flash('Venta no encontrada', 'error')
            return redirect(url_for('ventas.listar'))
        
        if venta.id_estado == 3:  # Already cancelled
            flash('Esta venta ya fue cancelada', 'warning')
            return redirect(url_for('ventas.ver', id=id))
        
        # Get sale details to revert inventory
        detalles = db.session.execute(
            select(DetalleVenta, Libros)
            .join(Libros, DetalleVenta.id_libro == Libros.id_libro)
            .where(DetalleVenta.id_venta == id)
        ).all()
        
        # Get sucursal from SAR parameter or use principal
        sucursal_id = get_sucursal_principal()
        if venta.id_parametro_sar:
            factura_sar = db.session.get(FacturasSar, venta.id_parametro_sar)
            if factura_sar:
                sucursal_id = factura_sar.id_sucursal
        
        # Revert inventory for each item
        for detalle, libro in detalles:
            libro.stock_fisico += detalle.cantidad
            
            # Create inventory adjustment
            crear_movimiento_inventario(
                libro_id=libro.id_libro,
                sucursal_id=sucursal_id,
                tipo_movimiento='Devolución',
                cantidad=detalle.cantidad,
                stock_anterior=libro.stock_fisico - detalle.cantidad,
                stock_nuevo=libro.stock_fisico,
                empleado_id=current_user.id_empleado,
                motivo='Cancelación de venta',
                referencia=f'CANCEL-VENTA-{venta.id_venta}',
                observaciones=f'Reversión automática por cancelación de venta #{venta.id_venta}'
            )
        
        # Update sale status to cancelled
        venta.id_estado = 3  # Estado: Cancelada
        
        # Mark SAR parameter as annulled if exists
        if venta.id_parametro_sar:
            factura_sar = db.session.get(FacturasSar, venta.id_parametro_sar)
            if factura_sar:
                factura_sar.anulada = 1
                factura_sar.fecha_anulacion = datetime.now()
        
        db.session.commit()
        
        flash('✅ Venta cancelada exitosamente. Inventario revertido.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cancelar venta: {str(e)}', 'error')

    return redirect(url_for('ventas.ver', id=id))