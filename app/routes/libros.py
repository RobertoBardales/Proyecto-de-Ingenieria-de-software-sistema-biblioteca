from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_
from models import (
    Libros, Autores, Categorias, Editoriales, 
    LibroAutores, LibroCategoria, LibroEditoriales, Resenas, Clientes,
    Inventarios, Sucursales, Empleados
)
from app import db
from datetime import datetime
import re

bp = Blueprint('libros', __name__, url_prefix='/libros')

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID disponible para Libros"""
    max_id = db.session.execute(
        select(func.max(Libros.id_libro))
    ).scalar()
    return (max_id or 0) + 1

def get_next_libro_autor_id():
    """Obtiene el siguiente ID disponible para LibroAutores"""
    max_id = db.session.execute(
        select(func.max(LibroAutores.id_libro_autor))
    ).scalar()
    return (max_id or 0) + 1

def get_next_libro_categoria_id():
    """Obtiene el siguiente ID disponible para LibroCategoria"""
    max_id = db.session.execute(
        select(func.max(LibroCategoria.id_libro_categoria))
    ).scalar()
    return (max_id or 0) + 1

def get_next_libro_editorial_id():
    """Obtiene el siguiente ID disponible para LibroEditoriales"""
    max_id = db.session.execute(
        select(func.max(LibroEditoriales.id_libros_editoriales))
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

def get_empleado_id():
    """Obtiene el ID del empleado actual o el primero activo"""
    if hasattr(current_user, 'id_empleado'):
        return current_user.id_empleado
    
    empleado = db.session.execute(
        select(Empleados).where(Empleados.activo == 1).limit(1)
    ).scalars().first()
    
    if not empleado:
        raise ValueError("No hay empleados activos en el sistema")
    
    return empleado.id_empleado

def registrar_stock_inicial(libro, empleado_id, sucursal_id):
    """Registra el stock inicial cuando se crea un libro nuevo"""
    
    # Registrar stock físico si existe
    if libro.stock_fisico > 0:
        movimiento_fisico = Inventarios(
            id_inventario=get_next_inventario_id(),
            id_libro=libro.id_libro,
            id_sucursal=sucursal_id,
            tipo_movimiento='Entrada',
            cantidad=libro.stock_fisico,
            stock_anterior=0,
            stock_nuevo=libro.stock_fisico,
            formato='Físico',
            fecha_movimiento=datetime.now(),
            id_empleado=empleado_id,
            motivo='Stock inicial al crear el libro',
            referencia=f'INICIAL-{libro.id_libro}',
            observaciones=f'Registro automático de stock inicial para "{libro.titulo}"'
        )
        db.session.add(movimiento_fisico)
    
    # Registrar stock digital si existe
    if libro.stock_digital > 0:
        movimiento_digital = Inventarios(
            id_inventario=get_next_inventario_id(),
            id_libro=libro.id_libro,
            id_sucursal=sucursal_id,
            tipo_movimiento='Entrada',
            cantidad=libro.stock_digital,
            stock_anterior=0,
            stock_nuevo=libro.stock_digital,
            formato='Digital',
            fecha_movimiento=datetime.now(),
            id_empleado=empleado_id,
            motivo='Stock inicial al crear el libro',
            referencia=f'INICIAL-{libro.id_libro}',
            observaciones=f'Registro automático de stock digital inicial para "{libro.titulo}"'
        )
        db.session.add(movimiento_digital)

def registrar_ajuste_stock(libro, stock_fisico_anterior, stock_digital_anterior, empleado_id, sucursal_id):
    """Registra movimientos de inventario cuando se edita el stock de un libro"""
    
    # Ajustar stock físico si cambió
    if libro.stock_fisico != stock_fisico_anterior:
        diferencia = libro.stock_fisico - stock_fisico_anterior
        tipo = 'Entrada' if diferencia > 0 else 'Salida'
        
        movimiento_fisico = Inventarios(
            id_inventario=get_next_inventario_id(),
            id_libro=libro.id_libro,
            id_sucursal=sucursal_id,
            tipo_movimiento='Ajuste',
            cantidad=abs(diferencia),
            stock_anterior=stock_fisico_anterior,
            stock_nuevo=libro.stock_fisico,
            formato='Físico',
            fecha_movimiento=datetime.now(),
            id_empleado=empleado_id,
            motivo=f'Ajuste manual de stock ({tipo.lower()}: {abs(diferencia)} unidades)',
            referencia=f'AJUSTE-{libro.id_libro}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            observaciones=f'Ajuste automático al editar el libro. Stock cambió de {stock_fisico_anterior} a {libro.stock_fisico}'
        )
        db.session.add(movimiento_fisico)
    
    # Ajustar stock digital si cambió
    if libro.stock_digital != stock_digital_anterior:
        diferencia = libro.stock_digital - stock_digital_anterior
        tipo = 'Entrada' if diferencia > 0 else 'Salida'
        
        movimiento_digital = Inventarios(
            id_inventario=get_next_inventario_id(),
            id_libro=libro.id_libro,
            id_sucursal=sucursal_id,
            tipo_movimiento='Ajuste',
            cantidad=abs(diferencia),
            stock_anterior=stock_digital_anterior,
            stock_nuevo=libro.stock_digital,
            formato='Digital',
            fecha_movimiento=datetime.now(),
            id_empleado=empleado_id,
            motivo=f'Ajuste manual de stock digital ({tipo.lower()}: {abs(diferencia)} unidades)',
            referencia=f'AJUSTE-{libro.id_libro}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            observaciones=f'Ajuste automático al editar el libro. Stock digital cambió de {stock_digital_anterior} a {libro.stock_digital}'
        )
        db.session.add(movimiento_digital)

def limpiar_texto(texto):
    """Limpia espacios múltiples preservando saltos de línea"""
    if not texto:
        return texto
    lines = texto.split('\n')
    cleaned_lines = [' '.join(line.split()) for line in lines]
    return '\n'.join(cleaned_lines)

def validar_isbn(isbn):
    """Valida formato ISBN-10 o ISBN-13"""
    isbn_clean = isbn.replace('-', '').replace(' ', '')
    
    if len(isbn_clean) not in [10, 13]:
        return False, 'ISBN debe tener 10 o 13 dígitos'
    
    if len(isbn_clean) == 10:
        if not (isbn_clean[:-1].isdigit() and (isbn_clean[-1].isdigit() or isbn_clean[-1].upper() == 'X')):
            return False, 'ISBN-10 inválido'
    else:
        if not isbn_clean.isdigit():
            return False, 'ISBN-13 debe contener solo dígitos'
    
    return True, None

def validar_libro_data(data, libro_id=None):
    """Valida los datos del libro"""
    errors = []
    
    titulo = data.get('titulo', '').strip()
    if not titulo or len(titulo) < 3:
        errors.append('El título debe tener al menos 3 caracteres')
    elif len(titulo) > 255:
        errors.append('El título no puede exceder 255 caracteres')
    
    isbn = data.get('isbn', '').strip()
    valido, error = validar_isbn(isbn)
    if not valido:
        errors.append(error)
    else:
        isbn_clean = isbn.replace('-', '').replace(' ', '')
        query = select(Libros).where(Libros.isbn == isbn_clean)
        if libro_id:
            query = query.where(Libros.id_libro != libro_id)
        existing = db.session.execute(query).first()
        if existing:
            errors.append('Este ISBN ya está registrado')
    
    try:
        num_pag = int(data.get('num_pag', 0))
        if num_pag <= 0:
            errors.append('El número de páginas debe ser mayor a 0')
    except ValueError:
        errors.append('Número de páginas inválido')
    
    try:
        stock_fisico = int(data.get('stock_fisico', 0))
        stock_digital = int(data.get('stock_digital', 0))
        if stock_fisico < 0 or stock_digital < 0:
            errors.append('El stock no puede ser negativo')
    except ValueError:
        errors.append('Stock inválido')
    
    try:
        precio_venta = float(data.get('precio_venta', 0))
        precio_prestamo = float(data.get('precio_prestamo', 0))
        if precio_venta < 0 or precio_prestamo < 0:
            errors.append('Los precios no pueden ser negativos')
    except ValueError:
        errors.append('Precios inválidos')
    
    return errors

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los libros con filtros (Storefront - muestra todos los libros disponibles)"""
    busqueda = request.args.get('busqueda', '').strip()
    categoria = request.args.get('categoria', '').strip()
    autor = request.args.get('autor', '').strip()
    formato = request.args.get('formato', '').strip()
    disponibilidad = request.args.get('disponibilidad', '').strip()
    orden = request.args.get('orden', 'titulo')
    
    # Base query - only show available books for storefront
    query = db.session.query(Libros).filter(
        or_(Libros.disp_venta == 1, Libros.disp_prestamo == 1)
    )
    
    if busqueda:
        query = query.filter(
            or_(
                Libros.titulo.ilike(f'%{busqueda}%'),
                Libros.isbn.ilike(f'%{busqueda}%'),
                Libros.descripcion.ilike(f'%{busqueda}%')
            )
        )
    
    if categoria:
        query = query.join(LibroCategoria).filter(
            LibroCategoria.id_categoria == int(categoria)
        )
    
    if autor:
        query = query.join(LibroAutores).filter(
            LibroAutores.id_autor == int(autor)
        )
    
    if formato:
        query = query.filter(Libros.formato == formato)
    
    if disponibilidad == 'venta':
        query = query.filter(Libros.disp_venta == 1)
    elif disponibilidad == 'prestamo':
        query = query.filter(Libros.disp_prestamo == 1)
    
    if orden == 'titulo':
        query = query.order_by(Libros.titulo.asc())
    elif orden == 'precio_asc':
        query = query.order_by(Libros.precio_venta.asc())
    elif orden == 'precio_desc':
        query = query.order_by(Libros.precio_venta.desc())
    elif orden == 'stock':
        query = query.order_by((Libros.stock_fisico + Libros.stock_digital).desc())
    else:
        query = query.order_by(Libros.id_libro.desc())
    
    libros = query.all()
    
    libros_data = []
    for libro in libros:
        autores = db.session.execute(
            select(Autores)
            .join(LibroAutores)
            .where(LibroAutores.id_libro == libro.id_libro)
        ).scalars().all()
        
        categorias_libro = db.session.execute(
            select(Categorias)
            .join(LibroCategoria)
            .where(LibroCategoria.id_libro == libro.id_libro)
        ).scalars().all()
        
        editorial = db.session.execute(
            select(Editoriales)
            .join(LibroEditoriales)
            .where(LibroEditoriales.id_libro == libro.id_libro)
        ).scalars().first()
        
        libros_data.append({
            'libro': libro,
            'autores': autores,
            'categorias': categorias_libro,
            'editorial': editorial
        })
    
    todas_categorias = db.session.execute(
        select(Categorias).order_by(Categorias.nombre)
    ).scalars().all()
    
    todos_autores = db.session.execute(
        select(Autores).order_by(Autores.apellidos, Autores.nombres)
    ).scalars().all()
    
    formatos_disponibles = ['Físico', 'Digital', 'Ambos']
    
    return render_template('libros/listar.html',
                         libros_data=libros_data,
                         todas_categorias=todas_categorias,
                         todos_autores=todos_autores,
                         formatos_disponibles=formatos_disponibles,
                         busqueda_actual=busqueda,
                         categoria_actual=categoria,
                         autor_actual=autor,
                         formato_actual=formato,
                         disponibilidad_actual=disponibilidad,
                         orden_actual=orden)

@bp.route('/listar2')
@login_required
def listar2():
    """Lista todos los libros con el nuevo diseño (Admin - solo muestra libros disponibles)"""
    
    # Only show books that are available for sale or loan
    query = db.session.query(Libros).filter(
        or_(Libros.disp_venta == 1, Libros.disp_prestamo == 1)
    ).order_by(Libros.titulo.asc())
    
    libros = query.all()
    
    libros_data = []
    for libro in libros:
        autores = db.session.execute(
            select(Autores)
            .join(LibroAutores)
            .where(LibroAutores.id_libro == libro.id_libro)
        ).scalars().all()
        
        categorias_libro = db.session.execute(
            select(Categorias)
            .join(LibroCategoria)
            .where(LibroCategoria.id_libro == libro.id_libro)
        ).scalars().all()
        
        editorial = db.session.execute(
            select(Editoriales)
            .join(LibroEditoriales)
            .where(LibroEditoriales.id_libro == libro.id_libro)
        ).scalars().first()
        
        libros_data.append({
            'libro': libro,
            'autores': autores,
            'categorias': categorias_libro,
            'editorial': editorial
        })
    
    todas_categorias = db.session.execute(
        select(Categorias).order_by(Categorias.nombre)
    ).scalars().all()
    
    todos_autores = db.session.execute(
        select(Autores).order_by(Autores.apellidos, Autores.nombres)
    ).scalars().all()
    
    return render_template('libros/listar2.html',
                         libros_data=libros_data,
                         todas_categorias=todas_categorias,
                         todos_autores=todos_autores)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalles completos de un libro"""
    libro = db.session.get(Libros, id)
    
    if not libro:
        flash('❌ Libro no encontrado', 'error')
        return redirect(url_for('libros.listar'))
    
    autores = db.session.execute(
        select(Autores)
        .join(LibroAutores)
        .where(LibroAutores.id_libro == id)
    ).scalars().all()
    
    categorias = db.session.execute(
        select(Categorias)
        .join(LibroCategoria)
        .where(LibroCategoria.id_libro == id)
    ).scalars().all()
    
    editorial = db.session.execute(
        select(Editoriales)
        .join(LibroEditoriales)
        .where(LibroEditoriales.id_libro == id)
    ).scalars().first()
    
    resenas = db.session.execute(
        select(Resenas, Clientes)
        .join(Clientes, Resenas.id_cliente == Clientes.id_cliente)
        .where(Resenas.id_libro == id)
        .where(Resenas.visible == True)
        .order_by(Resenas.fecha_resena.desc())
    ).all()
    
    calificacion_promedio = db.session.execute(
        select(func.avg(Resenas.calificacion))
        .where(Resenas.id_libro == id, Resenas.visible == True)
    ).scalar() or 0
    
    total_resenas = db.session.execute(
        select(func.count(Resenas.id_resena))
        .where(Resenas.id_libro == id, Resenas.visible == True)
    ).scalar() or 0
    
    usuario_ya_reseno = False
    if current_user.is_authenticated and current_user.tipo_usuario == 'cliente':
        usuario_ya_reseno = db.session.execute(
            select(Resenas).where(
                Resenas.id_libro == id,
                Resenas.id_cliente == current_user.id_cliente
            )
        ).scalars().first() is not None
    
    return render_template('libros/ver.html',
                         libro=libro,
                         autores=autores,
                         categorias=categorias,
                         editorial=editorial,
                         resenas=resenas,
                         calificacion_promedio=calificacion_promedio,
                         total_resenas=total_resenas,
                         usuario_ya_reseno=usuario_ya_reseno)

@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crear nuevo libro CON REGISTRO AUTOMÁTICO DE INVENTARIO"""
   
    if request.method == 'POST':
        try:
            errors = validar_libro_data(request.form)
            if errors:
                for error in errors:
                    flash(error, 'error')
                return redirect(url_for('libros.nuevo'))
            
            isbn_clean = request.form.get('isbn', '').replace('-', '').replace(' ', '')
            
            nuevo_libro = Libros(
                id_libro=get_next_id(),
                isbn=isbn_clean,
                titulo=limpiar_texto(request.form.get('titulo')),
                formato=request.form.get('formato'),
                num_pag=int(request.form.get('num_pag')),
                stock_fisico=int(request.form.get('stock_fisico', 0)),
                stock_digital=int(request.form.get('stock_digital', 0)),
                precio_venta=float(request.form.get('precio_venta')),
                precio_prestamo=float(request.form.get('precio_prestamo')),
                descripcion=limpiar_texto(request.form.get('descripcion', '')),
                observaciones=limpiar_texto(request.form.get('observaciones', '')),
                portada=request.form.get('portada', ''),
                disp_venta=1 if request.form.get('disp_venta') else 0,
                disp_prestamo=1 if request.form.get('disp_prestamo') else 0
            )
            
            db.session.add(nuevo_libro)
            
            # Add authors
            autores_ids = request.form.getlist('autores')
            for autor_id in autores_ids:
                if autor_id:
                    libro_autor = LibroAutores(
                        id_libro_autor=get_next_libro_autor_id(),
                        id_libro=nuevo_libro.id_libro,
                        id_autor=int(autor_id)
                    )
                    db.session.add(libro_autor)
            
            # Add categories
            categorias_ids = request.form.getlist('categorias')
            for categoria_id in categorias_ids:
                if categoria_id:
                    libro_categoria = LibroCategoria(
                        id_libro_categoria=get_next_libro_categoria_id(),
                        id_libro=nuevo_libro.id_libro,
                        id_categoria=int(categoria_id)
                    )
                    db.session.add(libro_categoria)
            
            # Add editorial
            editorial_id = request.form.get('editorial')
            if editorial_id:
                libro_editorial = LibroEditoriales(
                    id_libros_editoriales=get_next_libro_editorial_id(),
                    id_libro=nuevo_libro.id_libro,
                    id_editorial=int(editorial_id)
                )
                db.session.add(libro_editorial)
            
            # ✨ REGISTRAR STOCK INICIAL EN INVENTARIO
            empleado_id = get_empleado_id()
            sucursal_id = get_sucursal_principal()
            registrar_stock_inicial(nuevo_libro, empleado_id, sucursal_id)
            
            db.session.commit()
            
            flash(f'✅ Libro "{nuevo_libro.titulo}" creado exitosamente con registro de inventario', 'success')
            return redirect(url_for('libros.ver', id=nuevo_libro.id_libro))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error al crear libro: {str(e)}', 'error')
            return redirect(url_for('libros.nuevo'))
    
    autores = db.session.execute(
        select(Autores).order_by(Autores.apellidos, Autores.nombres)
    ).scalars().all()
    
    categorias = db.session.execute(
        select(Categorias).order_by(Categorias.nombre)
    ).scalars().all()
    
    editoriales = db.session.execute(
        select(Editoriales).order_by(Editoriales.nombre)
    ).scalars().all()
    
    formatos = ['Físico', 'Digital', 'Ambos']
    
    return render_template('libros/form.html',
                         autores=autores,
                         categorias=categorias,
                         editoriales=editoriales,
                         formatos=formatos)

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar libro existente CON REGISTRO AUTOMÁTICO DE AJUSTES DE INVENTARIO"""
    
    libro = db.session.get(Libros, id)
    
    if not libro:
        flash('❌ Libro no encontrado', 'error')
        return redirect(url_for('libros.listar'))
    
    if request.method == 'POST':
        try:
            errors = validar_libro_data(request.form, libro_id=id)
            if errors:
                for error in errors:
                    flash(error, 'error')
                return redirect(url_for('libros.editar', id=id))
            
            # ✨ GUARDAR STOCK ANTERIOR ANTES DE ACTUALIZAR
            stock_fisico_anterior = libro.stock_fisico
            stock_digital_anterior = libro.stock_digital
            
            isbn_clean = request.form.get('isbn', '').replace('-', '').replace(' ', '')
            
            libro.isbn = isbn_clean
            libro.titulo = limpiar_texto(request.form.get('titulo'))
            libro.formato = request.form.get('formato')
            libro.num_pag = int(request.form.get('num_pag'))
            libro.stock_fisico = int(request.form.get('stock_fisico', 0))
            libro.stock_digital = int(request.form.get('stock_digital', 0))
            libro.precio_venta = float(request.form.get('precio_venta'))
            libro.precio_prestamo = float(request.form.get('precio_prestamo'))
            libro.descripcion = limpiar_texto(request.form.get('descripcion', ''))
            libro.observaciones = limpiar_texto(request.form.get('observaciones', ''))
            libro.portada = request.form.get('portada', '')
            libro.disp_venta = 1 if request.form.get('disp_venta') else 0
            libro.disp_prestamo = 1 if request.form.get('disp_prestamo') else 0
            
            # Update authors
            db.session.execute(
                LibroAutores.__table__.delete().where(LibroAutores.id_libro == id)
            )
            autores_ids = request.form.getlist('autores')
            for autor_id in autores_ids:
                if autor_id:
                    libro_autor = LibroAutores(
                        id_libro_autor=get_next_libro_autor_id(),
                        id_libro=id,
                        id_autor=int(autor_id)
                    )
                    db.session.add(libro_autor)
            
            # Update categories
            db.session.execute(
                LibroCategoria.__table__.delete().where(LibroCategoria.id_libro == id)
            )
            categorias_ids = request.form.getlist('categorias')
            for categoria_id in categorias_ids:
                if categoria_id:
                    libro_categoria = LibroCategoria(
                        id_libro_categoria=get_next_libro_categoria_id(),
                        id_libro=id,
                        id_categoria=int(categoria_id)
                    )
                    db.session.add(libro_categoria)
            
            # Update editorial
            db.session.execute(
                LibroEditoriales.__table__.delete().where(LibroEditoriales.id_libro == id)
            )
            editorial_id = request.form.get('editorial')
            if editorial_id:
                libro_editorial = LibroEditoriales(
                    id_libros_editoriales=get_next_libro_editorial_id(),
                    id_libro=id,
                    id_editorial=int(editorial_id)
                )
                db.session.add(libro_editorial)
            
            # ✨ REGISTRAR AJUSTES DE STOCK EN INVENTARIO SI CAMBIÓ
            empleado_id = get_empleado_id()
            sucursal_id = get_sucursal_principal()
            registrar_ajuste_stock(libro, stock_fisico_anterior, stock_digital_anterior, empleado_id, sucursal_id)
            
            db.session.commit()
            
            flash(f'✅ Libro "{libro.titulo}" actualizado exitosamente con registro de inventario', 'success')
            return redirect(url_for('libros.ver', id=id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error al actualizar libro: {str(e)}', 'error')
            return redirect(url_for('libros.editar', id=id))
    
    autores_todos = db.session.execute(
        select(Autores).order_by(Autores.apellidos, Autores.nombres)
    ).scalars().all()
    
    categorias_todas = db.session.execute(
        select(Categorias).order_by(Categorias.nombre)
    ).scalars().all()
    
    editoriales_todas = db.session.execute(
        select(Editoriales).order_by(Editoriales.nombre)
    ).scalars().all()
    
    autores_libro = db.session.execute(
        select(Autores.id_autor)
        .join(LibroAutores)
        .where(LibroAutores.id_libro == id)
    ).scalars().all()
    
    categorias_libro = db.session.execute(
        select(Categorias.id_categoria)
        .join(LibroCategoria)
        .where(LibroCategoria.id_libro == id)
    ).scalars().all()
    
    editorial_libro = db.session.execute(
        select(Editoriales.id_editorial)
        .join(LibroEditoriales)
        .where(LibroEditoriales.id_libro == id)
    ).scalars().first()
    
    formatos = ['Físico', 'Digital', 'Ambos']
    
    return render_template('libros/form.html',
                         libro=libro,
                         autores=autores_todos,
                         categorias=categorias_todas,
                         editoriales=editoriales_todas,
                         formatos=formatos,
                         autores_seleccionados=autores_libro,
                         categorias_seleccionadas=categorias_libro,
                         editorial_seleccionada=editorial_libro)

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Eliminar libro (soft delete - marca como no disponible)"""
    
    try:
        libro = db.session.get(Libros, id)
        
        if not libro:
            flash('❌ Libro no encontrado', 'error')
            return redirect(url_for('libros.listar2'))
        
        # Store title for flash message
        titulo = libro.titulo
        
        # Soft delete - mark as unavailable and remove stock
        libro.disp_venta = 0
        libro.disp_prestamo = 0
        libro.stock_fisico = 0
        libro.stock_digital = 0
        db.session.commit()
        
        # Use warning category for delete operations (yellow/orange notification)
        flash(f'⚠️ Libro "{titulo}" eliminado exitosamente', 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al eliminar libro: {str(e)}', 'error')

    return redirect(url_for('libros.listar2'))