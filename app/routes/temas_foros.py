from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import select, func, desc
from models import TemasForos, Clientes, MensajesForos
from app import db
from datetime import datetime
import re

bp = Blueprint('temas_foros', __name__, url_prefix='/foros')

# Categorías predefinidas para los foros
CATEGORIAS_FOROS = [
    'General',
    'Recomendaciones de Libros',
    'Autores',
    'Géneros Literarios',
    'Eventos y Actividades',
    'Préstamos y Devoluciones',
    'Sugerencias',
    'Tecnología',
    'Ayuda',
    'Off-Topic'
]

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID disponible para TemasForos"""
    max_id = db.session.execute(
        select(func.max(TemasForos.id_tema))
    ).scalar()
    return (max_id or 0) + 1

def validar_titulo(titulo):
    """Valida el título del tema"""
    if not titulo or not titulo.strip():
        return False, 'El título es obligatorio'
    
    titulo = titulo.strip()
    
    # Longitud mínima y máxima
    if len(titulo) < 5:
        return False, 'El título debe tener al menos 5 caracteres'
    
    if len(titulo) > 255:
        return False, 'El título no puede exceder 255 caracteres'
    
    # No más de 2 espacios consecutivos
    if '   ' in titulo:
        return False, 'El título no puede tener más de 2 espacios consecutivos'
    
    # No más de 3 caracteres iguales seguidos
    if re.search(r'(.)\1{3,}', titulo):
        return False, 'El título no puede tener más de 3 caracteres iguales seguidos'
    
    return True, None

def validar_descripcion(descripcion):
    """Valida la descripción del tema"""
    if not descripcion or not descripcion.strip():
        return False, 'La descripción es obligatoria'
    
    descripcion = descripcion.strip()
    
    # Longitud mínima
    if len(descripcion) < 10:
        return False, 'La descripción debe tener al menos 10 caracteres'
    
    # Longitud máxima
    if len(descripcion) > 5000:
        return False, 'La descripción no puede exceder 5000 caracteres'
    
    return True, None

def incrementar_vistas(id_tema):
    """Incrementa el contador de vistas de un tema"""
    try:
        tema = db.session.get(TemasForos, id_tema)
        if tema:
            tema.vistas = (tema.vistas or 0) + 1
            db.session.commit()
    except:
        db.session.rollback()

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los temas del foro con filtros"""
    # Obtener filtros
    categoria = request.args.get('categoria', '')
    orden = request.args.get('orden', 'reciente')
    busqueda = request.args.get('busqueda', '')
    
    # Query base con joins
    query = select(TemasForos, Clientes)\
        .join(Clientes, TemasForos.id_cliente_creador == Clientes.id_cliente)\
        .where(TemasForos.activo == 1)
    
    # Aplicar filtro de categoría
    if categoria:
        query = query.where(TemasForos.categoria_foro == categoria)
    
    # Aplicar búsqueda
    if busqueda:
        query = query.where(
            TemasForos.titulo.contains(busqueda) | 
            TemasForos.descripcion.contains(busqueda)
        )
    
    # Aplicar orden
    if orden == 'reciente':
        query = query.order_by(desc(TemasForos.fecha_creacion))
    elif orden == 'popular':
        query = query.order_by(desc(TemasForos.vistas))
    elif orden == 'destacado':
        query = query.order_by(desc(TemasForos.destacado), desc(TemasForos.fecha_creacion))
    
    temas = db.session.execute(query).all()
    
    # Obtener conteo de mensajes por tema
    mensajes_count = {}
    for tema, _ in temas:
        count = db.session.execute(
            select(func.count(MensajesForos.id_mensaje))
            .where(MensajesForos.id_tema == tema.id_tema)
        ).scalar()
        mensajes_count[tema.id_tema] = count
    
    return render_template('temas_foros/listar.html', 
                         temas=temas,
                         mensajes_count=mensajes_count,
                         categorias=CATEGORIAS_FOROS,
                         categoria_actual=categoria,
                         orden_actual=orden,
                         busqueda_actual=busqueda)

@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crea un nuevo tema en el foro"""
    if request.method == 'POST':
        try:
            titulo = request.form.get('titulo', '').strip()
            categoria = request.form.get('categoria_foro', '')
            descripcion = request.form.get('descripcion', '').strip()
            destacado = request.form.get('destacado') == 'on'
            
            # Validar título
            valido, error = validar_titulo(titulo)
            if not valido:
                flash(error, 'error')
                return render_template('temas_foros/form.html', 
                                     categorias=CATEGORIAS_FOROS)
            
            # Validar categoría
            if categoria not in CATEGORIAS_FOROS:
                flash('Categoría inválida', 'error')
                return render_template('temas_foros/form.html', 
                                     categorias=CATEGORIAS_FOROS)
            
            # Validar descripción
            valido, error = validar_descripcion(descripcion)
            if not valido:
                flash(error, 'error')
                return render_template('temas_foros/form.html', 
                                     categorias=CATEGORIAS_FOROS)
            
            # Crear tema
            nuevo_tema = TemasForos(
                id_tema=get_next_id(),
                id_cliente_creador=current_user.id_cliente,
                categoria_foro=categoria,
                titulo=titulo,
                descripcion=descripcion,
                fecha_creacion=datetime.now(),
                activo=1,
                destacado=1 if destacado else 0,
                vistas=0
            )
            
            db.session.add(nuevo_tema)
            db.session.commit()
            
            flash(f'✅ Tema "{titulo}" creado exitosamente', 'success')
            return redirect(url_for('temas_foros.ver', id=nuevo_tema.id_tema))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear tema: {str(e)}', 'error')
            return render_template('temas_foros/form.html', 
                                 categorias=CATEGORIAS_FOROS)
    
    # GET
    return render_template('temas_foros/form.html', 
                         categorias=CATEGORIAS_FOROS)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver un tema específico con sus mensajes"""
    # Obtener tema con creador
    resultado = db.session.execute(
        select(TemasForos, Clientes)
        .join(Clientes, TemasForos.id_cliente_creador == Clientes.id_cliente)
        .where(TemasForos.id_tema == id)
    ).first()
    
    if not resultado:
        flash('Tema no encontrado', 'error')
        return redirect(url_for('temas_foros.listar'))
    
    tema, creador = resultado
    
    # Incrementar contador de vistas
    incrementar_vistas(id)
    
    # Obtener mensajes visibles del tema
    mensajes = db.session.execute(
        select(MensajesForos, Clientes)
        .join(Clientes, MensajesForos.id_cliente == Clientes.id_cliente)
        .where(MensajesForos.id_tema == id)
        .where(MensajesForos.visible == True)  # ← AGREGAR ESTO
        .order_by(MensajesForos.fecha_publicacion)  # ← CAMBIAR ESTO
    ).all()
    
    return render_template('temas_foros/ver.html', 
                         tema=tema,
                         creador=creador,
                         mensajes=mensajes)

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edita un tema existente"""
    tema = db.session.get(TemasForos, id)
    
    if not tema:
        flash('Tema no encontrado', 'error')
        return redirect(url_for('temas_foros.listar'))
    
    # Verificar que el usuario sea el creador o admin
    if tema.id_cliente_creador != current_user.id_cliente and current_user.tipo_usuario != 'admin':
        flash('No tienes permisos para editar este tema', 'error')
        return redirect(url_for('temas_foros.ver', id=id))
    
    if request.method == 'POST':
        try:
            titulo = request.form.get('titulo', '').strip()
            categoria = request.form.get('categoria_foro', '')
            descripcion = request.form.get('descripcion', '').strip()
            destacado = request.form.get('destacado') == 'on'
            
            # Validar título
            valido, error = validar_titulo(titulo)
            if not valido:
                flash(error, 'error')
                return render_template('temas_foros/form.html', 
                                     tema=tema,
                                     categorias=CATEGORIAS_FOROS)
            
            # Validar categoría
            if categoria not in CATEGORIAS_FOROS:
                flash('Categoría inválida', 'error')
                return render_template('temas_foros/form.html', 
                                     tema=tema,
                                     categorias=CATEGORIAS_FOROS)
            
            # Validar descripción
            valido, error = validar_descripcion(descripcion)
            if not valido:
                flash(error, 'error')
                return render_template('temas_foros/form.html', 
                                     tema=tema,
                                     categorias=CATEGORIAS_FOROS)
            
            # Actualizar tema
            tema.titulo = titulo
            tema.categoria_foro = categoria
            tema.descripcion = descripcion
            tema.destacado = 1 if destacado else 0
            
            db.session.commit()
            
            flash(f'✅ Tema "{titulo}" actualizado exitosamente', 'success')
            return redirect(url_for('temas_foros.ver', id=id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar tema: {str(e)}', 'error')
    
    # GET
    return render_template('temas_foros/form.html', 
                         tema=tema,
                         categorias=CATEGORIAS_FOROS)

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Desactiva un tema (soft delete)"""
    try:
        tema = db.session.get(TemasForos, id)
        
        if not tema:
            flash('Tema no encontrado', 'error')
            return redirect(url_for('temas_foros.listar'))
        
        # Verificar permisos
        if tema.id_cliente_creador != current_user.id_cliente and current_user.tipo_usuario != 'admin':
            flash('No tienes permisos para eliminar este tema', 'error')
            return redirect(url_for('temas_foros.ver', id=id))
        
        # Soft delete
        tema.activo = 0
        db.session.commit()
        
        flash(f'✅ Tema "{tema.titulo}" eliminado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar tema: {str(e)}', 'error')
    
    return redirect(url_for('temas_foros.listar'))

@bp.route('/destacar/<int:id>', methods=['POST'])
@login_required
def destacar(id):
    """Marca o desmarca un tema como destacado (solo admin)"""
    try:
        # Solo admins pueden destacar
        if current_user.tipo_usuario != 'admin':
            flash('No tienes permisos para destacar temas', 'error')
            return redirect(url_for('temas_foros.ver', id=id))
        
        tema = db.session.get(TemasForos, id)
        
        if not tema:
            flash('Tema no encontrado', 'error')
            return redirect(url_for('temas_foros.listar'))
        
        # Toggle destacado
        tema.destacado = 0 if tema.destacado else 1
        db.session.commit()
        
        estado = "destacado" if tema.destacado else "desmarcado"
        flash(f'✅ Tema "{tema.titulo}" {estado} exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al cambiar estado: {str(e)}', 'error')
    
    return redirect(url_for('temas_foros.ver', id=id))

# ================== ESTADÍSTICAS ==================

@bp.route('/mis-temas')
@login_required
def mis_temas():
    """Lista los temas creados por el usuario actual"""
    temas = db.session.execute(
        select(TemasForos)
        .where(TemasForos.id_cliente_creador == current_user.id_cliente)
        .where(TemasForos.activo == 1)
        .order_by(desc(TemasForos.fecha_creacion))
    ).scalars().all()
    
    # Obtener conteo de mensajes
    mensajes_count = {}
    for tema in temas:
        count = db.session.execute(
            select(func.count(MensajesForos.id_mensaje))
            .where(MensajesForos.id_tema == tema.id_tema)
        ).scalar()
        mensajes_count[tema.id_tema] = count
    
    return render_template('temas_foros/mis_temas.html', 
                         temas=temas,
                         mensajes_count=mensajes_count)