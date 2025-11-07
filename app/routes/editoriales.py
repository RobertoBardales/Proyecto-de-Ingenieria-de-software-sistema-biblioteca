from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app import db
from models import Editoriales, Pais
from sqlalchemy import func
from sqlalchemy.orm import joinedload
import re

editoriales_bp = Blueprint('editoriales', __name__, url_prefix='/editoriales')

def validar_nombre(nombre):
    """Validar nombre de la editorial con reglas estrictas"""
    if not nombre or not nombre.strip():
        return False, 'Nombre de la editorial es obligatorio'
    
    # Eliminar espacios múltiples para validación
    nombre_limpio = ' '.join(nombre.split())
    
    # No más de 2 espacios seguidos en el texto original
    if '   ' in nombre:  # 3 espacios
        return False, 'El nombre no puede tener más de 2 espacios consecutivos'
    
    # No más de 2 caracteres iguales seguidos
    if re.search(r'(.)\1{2,}', nombre_limpio):
        return False, 'El nombre no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    # Longitud
    if len(nombre_limpio) < 2:
        return False, 'El nombre debe tener al menos 2 caracteres'
    if len(nombre_limpio) > 150:
        return False, 'El nombre no puede exceder 150 caracteres'
    
    return True, None

def validar_email(email):
    """Validar formato de email con reglas específicas"""
    if not email or not email.strip():
        return False, 'Email es obligatorio'
    
    email = email.strip().lower()
    
    # Patrón básico de email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, 'Formato de email inválido'
    
    # Separar parte local (antes de @) y dominio (después de @)
    try:
        local, dominio = email.split('@')
    except:
        return False, 'Formato de email inválido'
    
    # Parte local: mínimo 2 caracteres antes del @
    if len(local) < 2:
        return False, 'El email debe tener al menos 2 caracteres antes del @'
    
    # Parte del dominio: máximo 8 caracteres antes del punto
    dominio_sin_extension = dominio.split('.')[0]
    if len(dominio_sin_extension) > 8:
        return False, 'El dominio del email no puede tener más de 8 caracteres antes del punto'
    
    # No más de 2 caracteres iguales seguidos
    if re.search(r'(.)\1{2,}', email):
        return False, 'El email no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    # Longitud total
    if len(email) > 100:
        return False, 'Email no puede exceder 100 caracteres'
    
    return True, None

def validar_telefono(telefono):
    """Validar formato de teléfono hondureño (+504 y debe empezar con 3, 7, 8 o 9)"""
    if not telefono or not telefono.strip():
        return False, 'Teléfono es obligatorio'
    
    # Limpiar espacios y guiones para validación
    telefono_limpio = telefono.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    # Debe empezar con +504 o solo el número
    if telefono_limpio.startswith('+504'):
        numero = telefono_limpio[4:]  # Quitar +504
    elif telefono_limpio.startswith('504'):
        numero = telefono_limpio[3:]  # Quitar 504
    else:
        numero = telefono_limpio
    
    # Validar que solo contenga dígitos después de limpiar
    if not numero.isdigit():
        return False, 'El teléfono solo puede contener números después del código de país'
    
    # Debe tener exactamente 8 dígitos
    if len(numero) != 8:
        return False, 'El número de teléfono debe tener exactamente 8 dígitos'
    
    # Debe empezar con 3, 7, 8 o 9
    if numero[0] not in ['3', '7', '8', '9']:
        return False, 'El número de teléfono debe empezar con 3, 7, 8 o 9'
    
    # Formato válido: debe incluir +504
    if not telefono_limpio.startswith('+504'):
        return False, 'El teléfono debe incluir el código de país +504 (ej: +504 9999-9999)'
    
    return True, None

def validar_direccion(direccion):
    """Validar dirección con límites de caracteres"""
    if not direccion or not direccion.strip():
        return True, None  # Dirección es opcional
    
    direccion = direccion.strip()
    
    # No más de 2 espacios consecutivos
    if '   ' in direccion:
        return False, 'La dirección no puede tener más de 2 espacios consecutivos'
    
    # No más de 2 caracteres iguales seguidos (excepto espacios)
    if re.search(r'([^\s])\1{2,}', direccion):
        return False, 'La dirección no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    # Longitud máxima
    if len(direccion) > 200:
        return False, 'La dirección no puede exceder 200 caracteres'
    
    # Mínimo 5 caracteres si se proporciona
    if len(direccion) < 5:
        return False, 'La dirección debe tener al menos 5 caracteres'
    
    return True, None

def get_next_id():
    """Obtener el siguiente ID disponible para editoriales"""
    ultimo_id = db.session.query(func.max(Editoriales.id_editorial)).scalar()
    return (ultimo_id or 0) + 1

# READ - Listar todas las editoriales
@editoriales_bp.route('/')
@login_required
def listar():
    # Cargar editoriales con sus países usando joinedload
    editoriales = db.session.query(Editoriales).options(
        joinedload(Editoriales.Pais_)
    ).order_by(Editoriales.nombre).all()
    
    return render_template('editoriales/listar.html', editoriales=editoriales)

# CREATE - Mostrar formulario de creación
@editoriales_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def crear():
    # Obtener todos los países para el select
    paises = db.session.query(Pais).order_by(Pais.nombre_pais).all()
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            id_pais = request.form.get('id_pais')
            telefono = request.form.get('telefono', '').strip()
            email = request.form.get('email', '').strip().lower()
            direccion = request.form.get('direccion', '').strip()
            
            # Validar nombre
            valido, error = validar_nombre(nombre)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Validar país
            if not id_pais:
                flash('Debes seleccionar un país.', 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Verificar que el país existe
            pais = db.session.get(Pais, int(id_pais))
            if not pais:
                flash('País seleccionado no válido.', 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Validar teléfono
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Validar email
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Verificar email duplicado
            email_existe = db.session.query(Editoriales).filter(
                func.lower(Editoriales.email) == email
            ).first()
            if email_existe:
                flash('Este email ya está registrado.', 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Validar dirección
            valido, error = validar_direccion(direccion)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=None, paises=paises)
            
            # Crear editorial
            nuevo_id = get_next_id()
            nueva_editorial = Editoriales(
                id_editorial=nuevo_id,
                nombre=nombre.title(),
                id_pais=int(id_pais),
                telefono=telefono,
                email=email,
                direccion=direccion if direccion else None
            )
            
            db.session.add(nueva_editorial)
            db.session.commit()
            
            flash(f'Editorial {nombre} creada exitosamente.', 'success')
            return redirect(url_for('editoriales.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear editorial: {str(e)}', 'error')
            print(f"Error en crear editorial: {str(e)}")
    
    return render_template('editoriales/form.html', editorial=None, paises=paises)

# UPDATE - Mostrar formulario de edición
@editoriales_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    # Obtener todos los países para el select
    paises = db.session.query(Pais).order_by(Pais.nombre_pais).all()
    
    # Cargar editorial con su país
    editorial = db.session.query(Editoriales).options(
        joinedload(Editoriales.Pais_)
    ).filter(Editoriales.id_editorial == id).first()
    
    if not editorial:
        flash('Editorial no encontrada.', 'error')
        return redirect(url_for('editoriales.listar'))
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            id_pais = request.form.get('id_pais')
            telefono = request.form.get('telefono', '').strip()
            email = request.form.get('email', '').strip().lower()
            direccion = request.form.get('direccion', '').strip()
            
            # Validar nombre
            valido, error = validar_nombre(nombre)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Validar país
            if not id_pais:
                flash('Debes seleccionar un país.', 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Verificar que el país existe
            pais = db.session.get(Pais, int(id_pais))
            if not pais:
                flash('País seleccionado no válido.', 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Validar teléfono
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Validar email
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Verificar email duplicado (excluyendo el actual)
            email_existe = db.session.query(Editoriales).filter(
                func.lower(Editoriales.email) == email,
                Editoriales.id_editorial != id
            ).first()
            if email_existe:
                flash('Este email ya está registrado.', 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Validar dirección
            valido, error = validar_direccion(direccion)
            if not valido:
                flash(error, 'error')
                return render_template('editoriales/form.html', editorial=editorial, paises=paises)
            
            # Actualizar datos
            editorial.nombre = nombre.title()
            editorial.id_pais = int(id_pais)
            editorial.telefono = telefono
            editorial.email = email
            editorial.direccion = direccion if direccion else None
            
            db.session.commit()
            flash(f'Editorial {nombre} actualizada exitosamente.', 'success')
            return redirect(url_for('editoriales.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar editorial: {str(e)}', 'error')
    
    return render_template('editoriales/form.html', editorial=editorial, paises=paises)

# DELETE - Eliminar editorial
@editoriales_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    try:
        editorial = db.session.get(Editoriales, id)
        if not editorial:
            flash('Editorial no encontrada.', 'error')
            return redirect(url_for('editoriales.listar'))
        
        # Verificar si la editorial tiene libros asociados
        if editorial.Libro_Editoriales:
            flash('No se puede eliminar la editorial porque tiene libros asociados.', 'error')
            return redirect(url_for('editoriales.listar'))
        
        nombre_editorial = editorial.nombre
        db.session.delete(editorial)
        db.session.commit()
        flash(f'Editorial {nombre_editorial} eliminada exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar editorial: {str(e)}', 'error')
    
    return redirect(url_for('editoriales.listar'))