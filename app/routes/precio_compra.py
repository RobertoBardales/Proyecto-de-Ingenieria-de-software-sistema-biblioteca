from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_, and_, desc
from models import PrecioCompraEditorial, Libros, Editoriales, LibroEditoriales
from app import db
from datetime import datetime
from decimal import Decimal
import traceback

bp = Blueprint('precio_compra', __name__, url_prefix='/precios-compra')

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID para precio compra"""
    max_id = db.session.execute(
        select(func.max(PrecioCompraEditorial.id_precio_compra))
    ).scalar()
    return (max_id or 0) + 1

def get_precio_compra(id_libro, id_editorial):
    """Obtiene el precio de compra de un libro para una editorial específica"""
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
    
    # Si no hay precio definido, usar 50% del precio de venta por defecto
    libro = db.session.get(Libros, id_libro)
    if libro:
        return libro.precio_venta * Decimal('0.50')
    
    return Decimal('0.00')

def get_libros_por_editorial(id_editorial):
    """
    Obtiene todos los libros de una editorial específica.
    Usa la tabla de relación Libro_Editoriales.
    """
    try:
        # Query directo con join a LibroEditoriales
        libros = db.session.query(Libros).join(
            LibroEditoriales,
            Libros.id_libro == LibroEditoriales.id_libro
        ).filter(
            LibroEditoriales.id_editorial == id_editorial
        ).order_by(Libros.titulo).all()
        
        print(f"📚 Editorial {id_editorial}: Encontrados {len(libros)} libros")
        
        return libros
        
    except Exception as e:
        print(f"❌ Error en get_libros_por_editorial: {str(e)}")
        traceback.print_exc()
        return []

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los precios de compra configurados"""
    editorial_filter = request.args.get('editorial', '').strip()
    busqueda = request.args.get('busqueda', '').strip()
    
    query = db.session.query(PrecioCompraEditorial).join(
        Libros, PrecioCompraEditorial.id_libro == Libros.id_libro
    ).join(
        Editoriales, PrecioCompraEditorial.id_editorial == Editoriales.id_editorial
    )
    
    if editorial_filter:
        query = query.filter(PrecioCompraEditorial.id_editorial == int(editorial_filter))
    
    if busqueda:
        search_term = f'%{busqueda}%'
        query = query.filter(
            or_(
                Libros.titulo.ilike(search_term),
                Libros.isbn.ilike(search_term),
                Editoriales.nombre.ilike(search_term)
            )
        )
    
    precios = query.order_by(desc(PrecioCompraEditorial.fecha_actualizacion)).all()
    
    editoriales = db.session.execute(
        select(Editoriales).order_by(Editoriales.nombre)
    ).scalars().all()
    
    return render_template('precio_compra/listar.html',
                         precios=precios,
                         editoriales=editoriales,
                         editorial_actual=editorial_filter,
                         busqueda_actual=busqueda)

@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crear nuevo precio de compra"""
    if request.method == 'POST':
        try:
            id_libro = request.form.get('id_libro')
            id_editorial = request.form.get('id_editorial')
            precio_compra = request.form.get('precio_compra')
            
            if not id_libro or not id_editorial or not precio_compra:
                flash('Todos los campos son requeridos', 'error')
                return redirect(url_for('precio_compra.nuevo'))
            
            # Verificar que el libro pertenece a la editorial
            libro_editorial = db.session.query(LibroEditoriales).filter(
                and_(
                    LibroEditoriales.id_libro == int(id_libro),
                    LibroEditoriales.id_editorial == int(id_editorial)
                )
            ).first()
            
            if not libro_editorial:
                flash('El libro seleccionado no pertenece a esta editorial', 'error')
                return redirect(url_for('precio_compra.nuevo'))
            
            # Verificar si ya existe un precio activo para esta combinación
            existe = db.session.execute(
                select(PrecioCompraEditorial)
                .where(
                    and_(
                        PrecioCompraEditorial.id_libro == int(id_libro),
                        PrecioCompraEditorial.id_editorial == int(id_editorial),
                        PrecioCompraEditorial.activo == 1
                    )
                )
            ).scalars().first()
            
            if existe:
                flash('Ya existe un precio activo para esta combinación libro-editorial', 'error')
                return redirect(url_for('precio_compra.nuevo'))
            
            nuevo_precio = PrecioCompraEditorial(
                id_precio_compra=get_next_id(),
                id_libro=int(id_libro),
                id_editorial=int(id_editorial),
                precio_compra=Decimal(precio_compra),
                fecha_actualizacion=datetime.now(),
                activo=1,
                observaciones=request.form.get('observaciones', '').strip()
            )
            
            db.session.add(nuevo_precio)
            db.session.commit()
            
            libro = db.session.get(Libros, int(id_libro))
            editorial = db.session.get(Editoriales, int(id_editorial))
            
            flash(f'✅ Precio de compra creado: {libro.titulo} - {editorial.nombre}', 'success')
            return redirect(url_for('precio_compra.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear precio: {str(e)}', 'error')
            print(f"❌ Error creando precio: {str(e)}")
            traceback.print_exc()
            return redirect(url_for('precio_compra.nuevo'))
    
    # GET - Solo cargar editoriales, los libros se cargarán dinámicamente
    editoriales = db.session.execute(
        select(Editoriales).order_by(Editoriales.nombre)
    ).scalars().all()
    
    return render_template('precio_compra/form.html',
                         editoriales=editoriales)

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar precio de compra existente"""
    precio = db.session.get(PrecioCompraEditorial, id)
    
    if not precio:
        flash('Precio no encontrado', 'error')
        return redirect(url_for('precio_compra.listar'))
    
    if request.method == 'POST':
        try:
            nuevo_precio_valor = request.form.get('precio_compra')
            
            if not nuevo_precio_valor:
                flash('El precio es requerido', 'error')
                return redirect(url_for('precio_compra.editar', id=id))
            
            precio.precio_compra = Decimal(nuevo_precio_valor)
            precio.fecha_actualizacion = datetime.now()
            precio.observaciones = request.form.get('observaciones', '').strip()
            
            db.session.commit()
            
            flash(f'✅ Precio actualizado exitosamente', 'success')
            return redirect(url_for('precio_compra.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar precio: {str(e)}', 'error')
            return redirect(url_for('precio_compra.editar', id=id))
    
    return render_template('precio_compra/form.html',
                         precio=precio)

@bp.route('/desactivar/<int:id>', methods=['POST'])
@login_required
def desactivar(id):
    """Desactivar un precio de compra"""
    try:
        precio = db.session.get(PrecioCompraEditorial, id)
        
        if not precio:
            flash('Precio no encontrado', 'error')
            return redirect(url_for('precio_compra.listar'))
        
        precio.activo = 0
        precio.fecha_actualizacion = datetime.now()
        
        db.session.commit()
        
        flash('✅ Precio desactivado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al desactivar precio: {str(e)}', 'error')
    
    return redirect(url_for('precio_compra.listar'))

@bp.route('/activar/<int:id>', methods=['POST'])
@login_required
def activar(id):
    """Activar un precio de compra"""
    try:
        precio = db.session.get(PrecioCompraEditorial, id)
        
        if not precio:
            flash('Precio no encontrado', 'error')
            return redirect(url_for('precio_compra.listar'))
        
        # Verificar que no haya otro precio activo para la misma combinación
        existe_activo = db.session.execute(
            select(PrecioCompraEditorial)
            .where(
                and_(
                    PrecioCompraEditorial.id_libro == precio.id_libro,
                    PrecioCompraEditorial.id_editorial == precio.id_editorial,
                    PrecioCompraEditorial.activo == 1,
                    PrecioCompraEditorial.id_precio_compra != id
                )
            )
        ).scalars().first()
        
        if existe_activo:
            flash('Ya existe un precio activo para esta combinación libro-editorial', 'error')
            return redirect(url_for('precio_compra.listar'))
        
        precio.activo = 1
        precio.fecha_actualizacion = datetime.now()
        
        db.session.commit()
        
        flash('✅ Precio activado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al activar precio: {str(e)}', 'error')
    
    return redirect(url_for('precio_compra.listar'))

# ================== API ENDPOINTS ==================

@bp.route('/api/libros-editorial/<int:editorial_id>')
@login_required
def api_libros_editorial(editorial_id):
    """API: Obtener libros de una editorial específica"""
    try:
        print(f"🔍 Buscando libros para editorial ID: {editorial_id}")
        
        # Verificar que la editorial existe
        editorial = db.session.get(Editoriales, editorial_id)
        if not editorial:
            print(f"❌ Editorial {editorial_id} no encontrada")
            return jsonify({'error': 'Editorial no encontrada'}), 404
        
        print(f"✅ Editorial encontrada: {editorial.nombre}")
        
        # Obtener libros
        libros = get_libros_por_editorial(editorial_id)
        
        if not libros:
            print(f"⚠️ No hay libros asociados a la editorial {editorial.nombre}")
            print(f"💡 Verifique que existan registros en la tabla Libro_Editoriales para editorial_id={editorial_id}")
            
        resultado = [{
            'id_libro': libro.id_libro,
            'titulo': libro.titulo,
            'isbn': libro.isbn,
            'precio_venta': float(libro.precio_venta),
            'stock_fisico': libro.stock_fisico,
            'stock_digital': libro.stock_digital
        } for libro in libros]
        
        print(f"📤 Devolviendo {len(resultado)} libros")
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Error en API libros-editorial: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'Error interno: {str(e)}'}), 500

@bp.route('/api/precio/<int:libro_id>/<int:editorial_id>')
@login_required
def api_get_precio(libro_id, editorial_id):
    """API: Obtener precio de compra de un libro para una editorial"""
    try:
        precio = get_precio_compra(libro_id, editorial_id)
        
        return jsonify({
            'precio_compra': float(precio)
        })
    except Exception as e:
        print(f"❌ Error obteniendo precio: {str(e)}")
        return jsonify({'error': str(e)}), 500

@bp.route('/api/precio-sugerido/<int:libro_id>')
@login_required
def api_precio_sugerido(libro_id):
    """API: Obtener precio sugerido (50% del precio de venta)"""
    try:
        libro = db.session.get(Libros, libro_id)
        
        if not libro:
            return jsonify({'error': 'Libro no encontrado'}), 404
        
        precio_sugerido = libro.precio_venta * Decimal('0.50')
        
        return jsonify({
            'precio_venta': float(libro.precio_venta),
            'precio_sugerido': float(precio_sugerido)
        })
    except Exception as e:
        print(f"❌ Error obteniendo precio sugerido: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ================== DEBUG ROUTES (Remove in production) ==================

@bp.route('/debug/editorial/<int:editorial_id>')
@login_required
def debug_editorial(editorial_id):
    """Debug: Ver información detallada sobre una editorial y sus libros"""
    try:
        # Verificar editorial
        editorial = db.session.get(Editoriales, editorial_id)
        if not editorial:
            return jsonify({'error': 'Editorial no encontrada'}), 404
        
        # Contar registros en Libro_Editoriales
        total_relaciones = db.session.query(func.count(LibroEditoriales.id_libros_editoriales)).filter(
            LibroEditoriales.id_editorial == editorial_id
        ).scalar()
        
        # Obtener todas las relaciones
        relaciones = db.session.query(LibroEditoriales).filter(
            LibroEditoriales.id_editorial == editorial_id
        ).all()
        
        # Obtener libros completos
        libros_info = []
        for rel in relaciones:
            libro = db.session.get(Libros, rel.id_libro)
            if libro:
                libros_info.append({
                    'id_libro': libro.id_libro,
                    'titulo': libro.titulo,
                    'isbn': libro.isbn,
                    'precio_venta': float(libro.precio_venta)
                })
        
        return jsonify({
            'editorial': {
                'id': editorial.id_editorial,
                'nombre': editorial.nombre
            },
            'total_relaciones_libro_editoriales': total_relaciones,
            'libros_encontrados': len(libros_info),
            'libros': libros_info
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@bp.route('/debug/check-data')
@login_required
def debug_check_data():
    """Debug: Ver estadísticas generales de las tablas"""
    try:
        total_editoriales = db.session.query(func.count(Editoriales.id_editorial)).scalar()
        total_libros = db.session.query(func.count(Libros.id_libro)).scalar()
        total_relaciones = db.session.query(func.count(LibroEditoriales.id_libros_editoriales)).scalar()
        total_precios = db.session.query(func.count(PrecioCompraEditorial.id_precio_compra)).scalar()
        
        # Editoriales con libros
        editoriales_con_libros = db.session.query(
            LibroEditoriales.id_editorial,
            func.count(LibroEditoriales.id_libro).label('total_libros')
        ).group_by(LibroEditoriales.id_editorial).all()
        
        editoriales_detalle = []
        for ed_id, total in editoriales_con_libros:
            ed = db.session.get(Editoriales, ed_id)
            if ed:
                editoriales_detalle.append({
                    'id': ed_id,
                    'nombre': ed.nombre,
                    'total_libros': total
                })
        
        return jsonify({
            'resumen': {
                'total_editoriales': total_editoriales,
                'total_libros': total_libros,
                'total_relaciones_libro_editorial': total_relaciones,
                'total_precios_configurados': total_precios
            },
            'editoriales_con_libros': editoriales_detalle,
            'nota': 'Si total_relaciones_libro_editorial es 0, necesitas asociar libros a editoriales primero'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500