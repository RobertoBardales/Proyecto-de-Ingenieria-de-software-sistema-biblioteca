from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from models import Pais
from sqlalchemy import func
import re

pais_bp = Blueprint('pais', __name__, url_prefix='/pais')

def validar_nombre_pais(nombre):
    """Validar nombre del país"""
    if not nombre or not nombre.strip():
        return False, 'Nombre del país es obligatorio'
    if not re.match(r'^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]+$', nombre):
        return False, 'Nombre del país solo puede contener letras y espacios'
    if len(nombre.strip()) < 2:
        return False, 'Nombre del país debe tener al menos 2 caracteres'
    if len(nombre.strip()) > 100:
        return False, 'Nombre del país no puede exceder 100 caracteres'
    return True, None

def validar_codigo_iso(codigo):
    """Validar código ISO del país"""
    if not codigo or not codigo.strip():
        return False, 'Código ISO es obligatorio'
    if not re.match(r'^[A-Z]{2,3}$', codigo.upper()):
        return False, 'Código ISO debe tener 2-3 letras mayúsculas (ej: HN, USA)'
    return True, None

def get_next_id():
    """Obtener el siguiente ID disponible para países"""
    ultimo_id = db.session.query(func.max(Pais.id_pais)).scalar()
    return (ultimo_id or 0) + 1

# READ - Listar todos los países
@pais_bp.route('/')
@login_required
def listar():
    paises = db.session.query(Pais).order_by(Pais.nombre_pais).all()
    return render_template('pais/listar.html', paises=paises)

# CREATE - Mostrar formulario de creación
@pais_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def crear():
    if request.method == 'POST':
        try:
            nombre_pais = request.form.get('nombre_pais', '').strip()
            codigo_iso = request.form.get('codigo_iso', '').strip().upper()
            
            # Validar nombre
            valido, error = validar_nombre_pais(nombre_pais)
            if not valido:
                flash(error, 'error')
                return render_template('pais/form.html', pais=None)
            
            # Validar código ISO
            valido, error = validar_codigo_iso(codigo_iso)
            if not valido:
                flash(error, 'error')
                return render_template('pais/form.html', pais=None)
            
            # Verificar si el nombre ya existe
            nombre_existe = db.session.query(Pais).filter(
                func.lower(Pais.nombre_pais) == nombre_pais.lower()
            ).first()
            if nombre_existe:
                flash('Este país ya está registrado.', 'error')
                return render_template('pais/form.html', pais=None)
            
            # Verificar si el código ISO ya existe
            codigo_existe = db.session.query(Pais).filter(
                func.upper(Pais.codigo_iso) == codigo_iso
            ).first()
            if codigo_existe:
                flash('Este código ISO ya está registrado.', 'error')
                return render_template('pais/form.html', pais=None)
            
            # Crear país
            nuevo_id = get_next_id()
            nuevo_pais = Pais(
                id_pais=nuevo_id,
                nombre_pais=nombre_pais.title(),
                codigo_iso=codigo_iso
            )
            
            db.session.add(nuevo_pais)
            db.session.commit()
            
            flash(f'País {nombre_pais} creado exitosamente.', 'success')
            return redirect(url_for('pais.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear país: {str(e)}', 'error')
    
    return render_template('pais/form.html', pais=None)

# UPDATE - Mostrar formulario de edición
@pais_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    pais = db.session.get(Pais, id)
    
    if not pais:
        flash('País no encontrado.', 'error')
        return redirect(url_for('pais.listar'))
    
    if request.method == 'POST':
        try:
            nombre_pais = request.form.get('nombre_pais', '').strip()
            codigo_iso = request.form.get('codigo_iso', '').strip().upper()
            
            # Validar nombre
            valido, error = validar_nombre_pais(nombre_pais)
            if not valido:
                flash(error, 'error')
                return render_template('pais/form.html', pais=pais)
            
            # Validar código ISO
            valido, error = validar_codigo_iso(codigo_iso)
            if not valido:
                flash(error, 'error')
                return render_template('pais/form.html', pais=pais)
            
            # Verificar si el nombre ya existe (excluyendo el actual)
            nombre_existe = db.session.query(Pais).filter(
                func.lower(Pais.nombre_pais) == nombre_pais.lower(),
                Pais.id_pais != id
            ).first()
            if nombre_existe:
                flash('Este país ya está registrado.', 'error')
                return render_template('pais/form.html', pais=pais)
            
            # Verificar si el código ISO ya existe (excluyendo el actual)
            codigo_existe = db.session.query(Pais).filter(
                func.upper(Pais.codigo_iso) == codigo_iso,
                Pais.id_pais != id
            ).first()
            if codigo_existe:
                flash('Este código ISO ya está registrado.', 'error')
                return render_template('pais/form.html', pais=pais)
            
            # Actualizar datos
            pais.nombre_pais = nombre_pais.title()
            pais.codigo_iso = codigo_iso
            
            db.session.commit()
            flash(f'País {nombre_pais} actualizado exitosamente.', 'success')
            return redirect(url_for('pais.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar país: {str(e)}', 'error')
    
    return render_template('pais/form.html', pais=pais)

# DELETE - Eliminar país
@pais_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    try:
        pais = db.session.get(Pais, id)
        if not pais:
            flash('País no encontrado.', 'error')
            return redirect(url_for('pais.listar'))
        
        # Verificar si el país tiene editoriales o empleados asociados
        if pais.Editoriales or pais.Empleados:
            flash('No se puede eliminar el país porque tiene registros asociados (editoriales o empleados).', 'error')
            return redirect(url_for('pais.listar'))
        
        nombre_pais = pais.nombre_pais
        db.session.delete(pais)
        db.session.commit()
        flash(f'País {nombre_pais} eliminado exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar país: {str(e)}', 'error')
    
    return redirect(url_for('pais.listar'))