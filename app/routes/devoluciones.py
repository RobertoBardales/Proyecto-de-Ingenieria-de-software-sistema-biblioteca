from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func, and_
from models import (
    Prestamos, DetallesPrestamos, Libros, Clientes, Empleados,
    Inventarios, Sucursales
)
from app import db
from datetime import datetime
from decimal import Decimal

bp = Blueprint('devoluciones', __name__, url_prefix='/devoluciones')

# ================== FUNCIONES AUXILIARES ==================

def puede_devolver_detalle_prestamo(detalle_prestamo):
    """
    Verifica si un detalle de préstamo puede ser devuelto
    Reglas:
    - El estado debe ser "Prestado" (activo)
    - No debe haber sido devuelto ya
    """
    if detalle_prestamo.estado != 'Prestado':
        return False, f"Este libro ya fue {detalle_prestamo.estado.lower()}"
    
    return True, None

def registrar_devolucion_inventario(libro, empleado_id, detalle_prestamo_id, prestamo_id):
    """Registra movimiento de inventario por devolución de préstamo"""
    
    # Determine format - prioritize physical if available
    if libro.formato in ['Físico', 'Ambos']:
        stock_anterior = libro.stock_fisico
        libro.stock_fisico += 1
        stock_nuevo = libro.stock_fisico
        formato = 'Físico'
    else:
        stock_anterior = libro.stock_digital
        libro.stock_digital += 1
        stock_nuevo = libro.stock_digital
        formato = 'Digital'
    
    # Get main branch
    sucursal = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).limit(1)
    ).scalars().first()
    
    if not sucursal:
        raise ValueError("No hay sucursales activas en el sistema")
    
    # Get next inventory ID
    max_id = db.session.execute(
        select(func.max(Inventarios.id_inventario))
    ).scalar() or 0
    
    # Create inventory movement
    movimiento = Inventarios(
        id_inventario=max_id + 1,
        id_libro=libro.id_libro,
        id_sucursal=sucursal.id_sucursal,
        tipo_movimiento='Devolución de Préstamo',
        cantidad=1,
        stock_anterior=stock_anterior,
        stock_nuevo=stock_nuevo,
        formato=formato,
        fecha_movimiento=datetime.now(),
        id_empleado=empleado_id,
        motivo='Devolución de libro prestado',
        referencia=f'DEVOLUCION-PRESTAMO-{prestamo_id}',
        observaciones=f'Devolución de préstamo detalle #{detalle_prestamo_id}'
    )
    
    db.session.add(movimiento)
    return movimiento

def get_empleado_actual():
    """Obtiene el empleado actual o uno por defecto"""
    if hasattr(current_user, 'id_empleado') and current_user.id_empleado:
        return current_user.id_empleado
    
    empleado = db.session.execute(
        select(Empleados).where(Empleados.activo == 1).limit(1)
    ).scalars().first()
    
    if not empleado:
        raise ValueError("No hay empleados activos para procesar la devolución")
    
    return empleado.id_empleado

def calcular_multa(fecha_devolucion_estimada):
    """Calcula multa por retraso en devolución"""
    dias_retraso = (datetime.now().date() - fecha_devolucion_estimada).days
    
    if dias_retraso <= 0:
        return Decimal(0)  # No multa si está a tiempo
    
    # L. 50 per day
    multa_por_dia = Decimal('50.00')
    return multa_por_dia * dias_retraso

# ================== RUTAS DEVOLUCIONES ==================

@bp.route('/')
@login_required
def listar():
    """Lista todas las devoluciones de préstamos del usuario"""
    
    if current_user.tipo_usuario == 'cliente':
        # Clients see only their returned books
        query = db.session.query(
            DetallesPrestamos, Prestamos, Libros, Clientes
        ).join(
            Prestamos, DetallesPrestamos.id_prestamos == Prestamos.id_prestamo
        ).join(
            Libros, DetallesPrestamos.id_libro == Libros.id_libro
        ).join(
            Clientes, Prestamos.id_cliente == Clientes.id_cliente
        ).filter(
            and_(
                Prestamos.id_cliente == current_user.id_cliente,
                DetallesPrestamos.estado == 'Devuelto'
            )
        )
    else:
        # Employees/admins see all returned books
        query = db.session.query(
            DetallesPrestamos, Prestamos, Libros, Clientes
        ).join(
            Prestamos, DetallesPrestamos.id_prestamos == Prestamos.id_prestamo
        ).join(
            Libros, DetallesPrestamos.id_libro == Libros.id_libro
        ).join(
            Clientes, Prestamos.id_cliente == Clientes.id_cliente
        ).filter(
            DetallesPrestamos.estado == 'Devuelto'
        )
    
    devoluciones = query.order_by(Prestamos.fecha_prestamo.desc()).all()
    
    return render_template('devoluciones/listar.html', devoluciones=devoluciones)

@bp.route('/solicitar/<int:detalle_prestamo_id>', methods=['GET', 'POST'])
@login_required
def solicitar(detalle_prestamo_id):
    """Procesar devolución de un libro prestado"""
    
    detalle_prestamo = db.session.get(DetallesPrestamos, detalle_prestamo_id)
    
    if not detalle_prestamo:
        flash('Préstamo no encontrado', 'error')
        return redirect(url_for('biblioteca_personal.mi_biblioteca'))
    
    prestamo = db.session.get(Prestamos, detalle_prestamo.id_prestamos)
    libro = db.session.get(Libros, detalle_prestamo.id_libro)
    cliente = db.session.get(Clientes, prestamo.id_cliente)
    
    # Check permissions - client can only return their own loans
    if current_user.tipo_usuario == 'cliente':
        if prestamo.id_cliente != current_user.id_cliente:
            flash('No tienes permisos para devolver este préstamo', 'error')
            return redirect(url_for('biblioteca_personal.mi_biblioteca'))
    
    # Check if can be returned
    puede_devolver, error = puede_devolver_detalle_prestamo(detalle_prestamo)
    if not puede_devolver:
        flash(error, 'error')
        return redirect(url_for('biblioteca_personal.mi_biblioteca'))
    
    if request.method == 'POST':
        try:
            observaciones = request.form.get('observaciones', '').strip()
            
            # Get current employee
            empleado_id = get_empleado_actual()
            
            # Calculate fine if overdue
            fecha_dev = detalle_prestamo.fecha_devolucion
            if isinstance(fecha_dev, datetime):
                fecha_dev = fecha_dev.date()
            multa = calcular_multa(fecha_dev)
            
            # Record inventory movement
            registrar_devolucion_inventario(
                libro, 
                empleado_id, 
                detalle_prestamo_id,
                prestamo.id_prestamo
            )
            
            # Update detail status
            detalle_prestamo.estado = 'Devuelto'
            detalle_prestamo.multa = multa
            
            # Update main loan status - check if all books are returned
            todos_devueltos = db.session.execute(
                select(func.count(DetallesPrestamos.id_detalle_prestamos))
                .where(
                    and_(
                        DetallesPrestamos.id_prestamos == prestamo.id_prestamo,
                        DetallesPrestamos.estado != 'Devuelto'
                    )
                )
            ).scalar() == 0
            
            if todos_devueltos:
                prestamo.estado = 'Completado'
                prestamo.fecha_devolucion_real = datetime.now()
            
            # Add notes
            if observaciones:
                existing_obs = detalle_prestamo.observaciones or ""
                detalle_prestamo.observaciones = f"{existing_obs}\n[DEVUELTO {datetime.now().strftime('%d/%m/%Y %H:%M')}] {observaciones}".strip()
            else:
                detalle_prestamo.observaciones = f"[DEVUELTO {datetime.now().strftime('%d/%m/%Y %H:%M')}]"
            
            db.session.commit()
            
            # Flash message with fine info
            mensaje = f'✅ Devolución procesada exitosamente'
            if multa > 0:
                mensaje += f'\n⚠️ Multa por retraso: L. {multa:.2f}'
            
            flash(mensaje, 'success')
            return redirect(url_for('biblioteca_personal.mi_biblioteca'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al procesar devolución: {str(e)}', 'error')
            return redirect(url_for('devoluciones.solicitar', detalle_prestamo_id=detalle_prestamo_id))
    
    # GET - Show return form
    fecha_dev = detalle_prestamo.fecha_devolucion
    if isinstance(fecha_dev, datetime):
        fecha_dev = fecha_dev.date()
    
    dias_faltantes = (fecha_dev - datetime.now().date()).days
    esta_vencido = dias_faltantes < 0
    multa_estimada = calcular_multa(fecha_dev) if esta_vencido else Decimal(0)
    
    return render_template('devoluciones/solicitar.html',
                         detalle_prestamo=detalle_prestamo,
                         prestamo=prestamo,
                         libro=libro,
                         cliente=cliente,
                         dias_faltantes=abs(dias_faltantes),
                         esta_vencido=esta_vencido,
                         multa_estimada=multa_estimada)

@bp.route('/politica')
def politica():
    """Política de devoluciones de préstamos"""
    return render_template('devoluciones/politica.html')