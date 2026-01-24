from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_, and_
from models import (
    Venta, DetalleVenta, Libros, Clientes, Prestamos, DetallesPrestamos,
    LibroAutores, Autores, LibroCategoria, Categorias
)
from app import db
from datetime import datetime

# Blueprint definition
bp = Blueprint('biblioteca_personal', __name__, url_prefix='/biblioteca-personal')

# ================== MI BIBLIOTECA (MAIN VIEW) ==================

@bp.route('/')
@login_required
def mi_biblioteca():
    """Ver biblioteca personal del usuario (libros COMPRADOS y PRESTADOS)"""
    
    # Only clients can have a personal library
    if current_user.tipo_usuario != 'cliente':
        flash('Esta funcionalidad es solo para clientes', 'info')
        return redirect(url_for('libros.listar'))
    
    cliente_id = current_user.id_cliente
    
    # Get filter parameters
    busqueda = request.args.get('busqueda', '').strip()
    categoria = request.args.get('categoria', '').strip()
    formato = request.args.get('formato', '').strip()
    orden = request.args.get('orden', 'reciente')
    tipo = request.args.get('tipo', '')  # 'compra', 'prestamo', or empty for all
    
    libros_comprados = {}
    
    # ========== GET PURCHASED BOOKS ==========
    query_compras = db.session.query(
        DetalleVenta, 
        Libros, 
        Venta
    ).join(
        Libros, DetalleVenta.id_libro == Libros.id_libro
    ).join(
        Venta, DetalleVenta.id_venta == Venta.id_venta
    ).filter(
        Venta.id_cliente == cliente_id,
        Venta.id_estado.in_([1, 2])  # Only completed/paid sales
    )
    
    # Apply filters to purchases
    if busqueda:
        query_compras = query_compras.filter(
            or_(
                Libros.titulo.ilike(f'%{busqueda}%'),
                Libros.isbn.ilike(f'%{busqueda}%')
            )
        )
    
    if categoria:
        query_compras = query_compras.join(LibroCategoria).filter(
            LibroCategoria.id_categoria == int(categoria)
        )
    
    if formato:
        query_compras = query_compras.filter(Libros.formato == formato)
    
    # Only include purchases if tipo is empty or 'compra'
    if tipo == '' or tipo == 'compra':
        resultados_compras = query_compras.all()
        
        for detalle, libro, venta in resultados_compras:
            libro_id = libro.id_libro
            
            if libro_id not in libros_comprados:
                # Get authors
                autores = db.session.execute(
                    select(Autores)
                    .join(LibroAutores)
                    .where(LibroAutores.id_libro == libro_id)
                ).scalars().all()
                
                # Get categories
                categorias = db.session.execute(
                    select(Categorias)
                    .join(LibroCategoria)
                    .where(LibroCategoria.id_libro == libro_id)
                ).scalars().all()
                
                libros_comprados[libro_id] = {
                    'libro': libro,
                    'autores': autores,
                    'categorias': categorias,
                    'compras': [],
                    'prestamos': [],
                    'cantidad_total': 0,
                    'primera_compra': venta.fecha_venta,
                    'ultima_compra': venta.fecha_venta,
                    'primer_prestamo': None,
                    'ultimo_prestamo': None
                }
            
            # Add purchase info
            libros_comprados[libro_id]['compras'].append({
                'venta_id': venta.id_venta,
                'fecha': venta.fecha_venta,
                'cantidad': detalle.cantidad,
                'precio': detalle.precio_unitario,
                'numero_factura': venta.numero_factura
            })
            
            libros_comprados[libro_id]['cantidad_total'] += detalle.cantidad
            
            # Update dates
            if venta.fecha_venta < libros_comprados[libro_id]['primera_compra']:
                libros_comprados[libro_id]['primera_compra'] = venta.fecha_venta
            if venta.fecha_venta > libros_comprados[libro_id]['ultima_compra']:
                libros_comprados[libro_id]['ultima_compra'] = venta.fecha_venta
    
    # ========== GET LOANED BOOKS ==========
    if tipo == '' or tipo == 'prestamo':
        query_prestamos = db.session.query(
            DetallesPrestamos,
            Libros,
            Prestamos
        ).join(
            Libros, DetallesPrestamos.id_libro == Libros.id_libro
        ).join(
            Prestamos, DetallesPrestamos.id_prestamos == Prestamos.id_prestamo
        ).filter(
            Prestamos.id_cliente == cliente_id,
            DetallesPrestamos.estado == 'Prestado'
        )
        
        # Apply filters to loans
        if busqueda:
            query_prestamos = query_prestamos.filter(
                or_(
                    Libros.titulo.ilike(f'%{busqueda}%'),
                    Libros.isbn.ilike(f'%{busqueda}%')
                )
            )
        
        if categoria:
            query_prestamos = query_prestamos.join(LibroCategoria).filter(
                LibroCategoria.id_categoria == int(categoria)
            )
        
        if formato:
            query_prestamos = query_prestamos.filter(Libros.formato == formato)
        
        resultados_prestamos = query_prestamos.all()
        
        for detalle, libro, prestamo in resultados_prestamos:
            libro_id = libro.id_libro
            
            if libro_id not in libros_comprados:
                # Get authors
                autores = db.session.execute(
                    select(Autores)
                    .join(LibroAutores)
                    .where(LibroAutores.id_libro == libro_id)
                ).scalars().all()
                
                # Get categories
                categorias = db.session.execute(
                    select(Categorias)
                    .join(LibroCategoria)
                    .where(LibroCategoria.id_libro == libro_id)
                ).scalars().all()
                
                libros_comprados[libro_id] = {
                    'libro': libro,
                    'autores': autores,
                    'categorias': categorias,
                    'compras': [],
                    'prestamos': [],
                    'cantidad_total': 0,
                    'primera_compra': None,
                    'ultima_compra': None,
                    'primer_prestamo': prestamo.fecha_prestamo,
                    'ultimo_prestamo': prestamo.fecha_prestamo
                }
            
            # Add loan info
            libros_comprados[libro_id]['prestamos'].append({
                'prestamo_id': prestamo.id_prestamo,
                'fecha_prestamo': prestamo.fecha_prestamo,
                'fecha_devolucion_estimada': prestamo.fecha_devolucion_estimada,
                'fecha_devolucion_real': prestamo.fecha_devolucion_real,
                'estado': prestamo.estado,
                'estado_detalle': detalle.estado,
                'multa': detalle.multa or 0
            })
            
            # Update loan dates
            if libros_comprados[libro_id]['primer_prestamo'] is None or prestamo.fecha_prestamo < libros_comprados[libro_id]['primer_prestamo']:
                libros_comprados[libro_id]['primer_prestamo'] = prestamo.fecha_prestamo
            if libros_comprados[libro_id]['ultimo_prestamo'] is None or prestamo.fecha_prestamo > libros_comprados[libro_id]['ultimo_prestamo']:
                libros_comprados[libro_id]['ultimo_prestamo'] = prestamo.fecha_prestamo
    
    # Convert dict to list for template
    libros_data = list(libros_comprados.values())
    
    # Apply ordering
    if orden == 'reciente':
        libros_data.sort(key=lambda x: max(
            x['ultima_compra'] or datetime.min,
            x['ultimo_prestamo'] or datetime.min
        ), reverse=True)
    elif orden == 'titulo':
        libros_data.sort(key=lambda x: x['libro'].titulo)
    
    # Get all categories for filter
    todas_categorias = db.session.execute(
        select(Categorias).order_by(Categorias.nombre)
    ).scalars().all()
    
    formatos_disponibles = ['Físico', 'Digital', 'Ambos']
    
    # Calculate statistics
    total_libros = len(libros_data)
    total_compras = sum([len(libro['compras']) for libro in libros_data])
    total_prestamos = sum([len(libro['prestamos']) for libro in libros_data])
    
    total_gastado = db.session.execute(
        select(func.sum(Venta.total))
        .where(
            Venta.id_cliente == cliente_id,
            Venta.id_estado.in_([1, 2])
        )
    ).scalar() or 0
    
    estadisticas = {
        'total_libros': total_libros,
        'total_compras': total_compras,
        'total_prestamos': total_prestamos,
        'total_gastado': total_gastado
    }
    
    return render_template('biblioteca_personal/mi_biblioteca.html',
                         libros_data=libros_data,
                         todas_categorias=todas_categorias,
                         formatos_disponibles=formatos_disponibles,
                         estadisticas=estadisticas,
                         busqueda_actual=busqueda,
                         categoria_actual=categoria,
                         formato_actual=formato,
                         orden_actual=orden,
                         tipo_actual=tipo)

# ================== VER LIBRO INDIVIDUAL ==================

@bp.route('/libro/<int:libro_id>')
@login_required
def ver_libro_biblioteca(libro_id):
    """Ver detalles de un libro en mi biblioteca con historial de compras"""
    
    if current_user.tipo_usuario != 'cliente':
        flash('Esta funcionalidad es solo para clientes', 'info')
        return redirect(url_for('libros.ver', id=libro_id))
    
    cliente_id = current_user.id_cliente
    
    # Get book
    libro = db.session.get(Libros, libro_id)
    if not libro:
        flash('Libro no encontrado', 'error')
        return redirect(url_for('biblioteca_personal.mi_biblioteca'))
    
    # Check if user owns this book (has purchased it)
    compras = db.session.execute(
        select(DetalleVenta, Venta)
        .join(Venta, DetalleVenta.id_venta == Venta.id_venta)
        .where(
            DetalleVenta.id_libro == libro_id,
            Venta.id_cliente == cliente_id,
            Venta.id_estado.in_([1, 2])
        )
        .order_by(Venta.fecha_venta.desc())
    ).all()
    
    # Check if user has borrowed this book
    prestamos = db.session.execute(
        select(DetallesPrestamos, Prestamos)
        .join(Prestamos, DetallesPrestamos.id_prestamos == Prestamos.id_prestamo)
        .where(
            DetallesPrestamos.id_libro == libro_id,
            Prestamos.id_cliente == cliente_id
        )
        .order_by(Prestamos.fecha_prestamo.desc())
    ).all()
    
    if not compras and not prestamos:
        flash('No has comprado ni prestado este libro.', 'warning')
        return redirect(url_for('biblioteca_personal.mi_biblioteca'))
    
    # Get authors
    autores = db.session.execute(
        select(Autores)
        .join(LibroAutores)
        .where(LibroAutores.id_libro == libro_id)
    ).scalars().all()
    
    # Get categories
    categorias = db.session.execute(
        select(Categorias)
        .join(LibroCategoria)
        .where(LibroCategoria.id_libro == libro_id)
    ).scalars().all()
    
    # Calculate totals
    cantidad_total = sum([detalle.cantidad for detalle, _ in compras])
    total_gastado = sum([detalle.subtotal for detalle, _ in compras])
    
    return render_template('biblioteca_personal/ver_libro.html',
                         libro=libro,
                         autores=autores,
                         categorias=categorias,
                         compras=compras,
                         prestamos=prestamos,
                         cantidad_total=cantidad_total,
                         total_gastado=total_gastado,
                         fecha_actual=datetime.now().date())

# ================== DESCARGAR LIBRO DIGITAL ==================

@bp.route('/descargar/<int:libro_id>')
@login_required
def descargar_libro(libro_id):
    """Descargar libro digital (placeholder - implementar según tu sistema)"""
    
    if current_user.tipo_usuario != 'cliente':
        flash('Esta funcionalidad es solo para clientes', 'info')
        return redirect(url_for('libros.ver', id=libro_id))
    
    cliente_id = current_user.id_cliente
    
    # Check if user owns this book
    compra = db.session.execute(
        select(DetalleVenta, Venta, Libros)
        .join(Venta, DetalleVenta.id_venta == Venta.id_venta)
        .join(Libros, DetalleVenta.id_libro == Libros.id_libro)
        .where(
            DetalleVenta.id_libro == libro_id,
            Venta.id_cliente == cliente_id,
            Venta.id_estado.in_([1, 2])
        )
    ).first()
    
    if not compra:
        flash('No has comprado este libro', 'error')
        return redirect(url_for('biblioteca_personal.mi_biblioteca'))
    
    detalle, venta, libro = compra
    
    # Check if it's a digital book
    if libro.formato not in ['Digital', 'Ambos']:
        flash('Este libro no está disponible en formato digital', 'warning')
        return redirect(url_for('biblioteca_personal.ver_libro_biblioteca', libro_id=libro_id))
    
    # TODO: Implement actual file download
    # For now, just show a success message
    flash(f'📥 Descarga de "{libro.titulo}" iniciada (placeholder - implementar descarga real)', 'success')
    
    return redirect(url_for('biblioteca_personal.ver_libro_biblioteca', libro_id=libro_id))