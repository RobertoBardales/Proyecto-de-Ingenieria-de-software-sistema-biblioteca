from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required
from app import db
from models import Sucursales
from sqlalchemy import func
import re

sucursales_bp = Blueprint('sucursales', __name__, url_prefix='/sucursales')

def validar_nombre(nombre):
    """Validar nombre de sucursal"""
    if not nombre or not nombre.strip():
        return False, 'El nombre es obligatorio'
    
    nombre = nombre.strip()
    
    # No más de 2 espacios consecutivos
    if '   ' in nombre:
        return False, 'El nombre no puede tener más de 2 espacios consecutivos'
    
    # No más de 2 caracteres iguales seguidos
    if re.search(r'(.)\1{2,}', nombre):
        return False, 'El nombre no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    # Longitud
    if len(nombre) < 3:
        return False, 'El nombre debe tener al menos 3 caracteres'
    if len(nombre) > 100:
        return False, 'El nombre no puede exceder 100 caracteres'
    
    return True, None

def validar_email(email):
    """Validar formato de email"""
    if not email or not email.strip():
        return False, 'Email es obligatorio'
    
    email = email.strip().lower()
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, 'Formato de email inválido'
    
    try:
        local, dominio = email.split('@')
    except:
        return False, 'Formato de email inválido'
    
    if len(local) < 2:
        return False, 'El email debe tener al menos 2 caracteres antes del @'
    
    dominio_sin_extension = dominio.split('.')[0]
    if len(dominio_sin_extension) > 8:
        return False, 'El dominio del email no puede tener más de 8 caracteres antes del punto'
    
    if re.search(r'(.)\1{2,}', email):
        return False, 'El email no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    if len(email) > 100:
        return False, 'Email no puede exceder 100 caracteres'
    
    return True, None

def validar_telefono(telefono):
    """Validar formato de teléfono hondureño"""
    if not telefono or not telefono.strip():
        return False, 'El teléfono es obligatorio'
    
    telefono_limpio = telefono.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    if telefono_limpio.startswith('+504'):
        numero = telefono_limpio[4:]
    elif telefono_limpio.startswith('504'):
        numero = telefono_limpio[3:]
    else:
        numero = telefono_limpio
    
    if not numero.isdigit():
        return False, 'El teléfono solo puede contener números después del código de país'
    
    if len(numero) != 8:
        return False, 'El número de teléfono debe tener exactamente 8 dígitos'
    
    if numero[0] not in ['2', '3', '7', '8', '9']:
        return False, 'El número de teléfono debe empezar con 2, 3, 7, 8 o 9'
    
    if re.search(r'(\d)\1{2,}', numero):
        return False, 'El teléfono no puede tener el mismo dígito repetido más de 2 veces seguidas'
    
    if not telefono_limpio.startswith('+504'):
        return False, 'El teléfono debe incluir el código de país +504'
    
    return True, None

def validar_direccion(direccion):
    """Validar dirección"""
    if not direccion or not direccion.strip():
        return False, 'La dirección es obligatoria'
    
    direccion = direccion.strip()
    
    if '   ' in direccion:
        return False, 'La dirección no puede tener más de 2 espacios consecutivos'
    
    if re.search(r'([^\s])\1{2,}', direccion):
        return False, 'La dirección no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    if len(direccion) < 10:
        return False, 'La dirección debe tener al menos 10 caracteres'
    
    if len(direccion) > 200:
        return False, 'La dirección no puede exceder 200 caracteres'
    
    return True, None

def validar_ciudad(ciudad):
    """Validar ciudad"""
    if not ciudad or not ciudad.strip():
        return False, 'La ciudad es obligatoria'
    
    ciudad = ciudad.strip()
    
    if not re.match(r'^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]+$', ciudad):
        return False, 'La ciudad solo puede contener letras y espacios'
    
    if '   ' in ciudad:
        return False, 'La ciudad no puede tener más de 2 espacios consecutivos'
    
    if re.search(r'(.)\1{2,}', ciudad):
        return False, 'La ciudad no puede tener la misma letra repetida más de 2 veces seguidas'
    
    if len(ciudad) < 3:
        return False, 'La ciudad debe tener al menos 3 caracteres'
    
    if len(ciudad) > 50:
        return False, 'La ciudad no puede exceder 50 caracteres'
    
    return True, None

def validar_departamento(departamento):
    """Validar departamento"""
    if not departamento or not departamento.strip():
        return False, 'El departamento es obligatorio'
    
    departamento = departamento.strip()
    
    if not re.match(r'^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]+$', departamento):
        return False, 'El departamento solo puede contener letras y espacios'
    
    if '   ' in departamento:
        return False, 'El departamento no puede tener más de 2 espacios consecutivos'
    
    if re.search(r'(.)\1{2,}', departamento):
        return False, 'El departamento no puede tener la misma letra repetida más de 2 veces seguidas'
    
    if len(departamento) < 3:
        return False, 'El departamento debe tener al menos 3 caracteres'
    
    if len(departamento) > 50:
        return False, 'El departamento no puede exceder 50 caracteres'
    
    return True, None

def validar_codigo_postal(codigo):
    """Validar código postal hondureño"""
    if not codigo or not codigo.strip():
        return False, 'El código postal es obligatorio'
    
    codigo = codigo.strip()
    
    # Honduras usa códigos como 11101, puede tener guiones
    if not re.match(r'^[\d\-]+$', codigo):
        return False, 'El código postal solo puede contener números y guiones'
    
    if len(codigo) < 5:
        return False, 'El código postal debe tener al menos 5 caracteres'
    
    if len(codigo) > 10:
        return False, 'El código postal no puede exceder 10 caracteres'
    
    return True, None

def validar_observaciones(observaciones):
    """Validar observaciones"""
    if not observaciones:
        return True, None
    
    observaciones = observaciones.strip()
    
    if '   ' in observaciones:
        return False, 'Las observaciones no pueden tener más de 2 espacios consecutivos'
    
    if len(observaciones) > 500:
        return False, 'Las observaciones no pueden exceder 500 caracteres'
    
    return True, None

def get_next_id():
    """Obtener el siguiente ID disponible para sucursales"""
    ultimo_id = db.session.query(func.max(Sucursales.id_sucursal)).scalar()
    return (ultimo_id or 0) + 1

# API para crear desde modal
@sucursales_bp.route('/crear-rapido', methods=['POST'])
@login_required
def crear_rapido():
    """Crear sucursal desde modal - devuelve JSON"""
    try:
        nombre = request.form.get('nombre', '').strip()
        ciudad = request.form.get('ciudad', '').strip()
        
        # Validar nombre
        valido, error = validar_nombre(nombre)
        if not valido:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validar ciudad
        valido, error = validar_ciudad(ciudad)
        if not valido:
            return jsonify({'success': False, 'error': error}), 400
        
        # Validar nombre único
        existe = db.session.query(Sucursales).filter_by(nombre=nombre).first()
        if existe:
            return jsonify({'success': False, 'error': 'Ya existe una sucursal con ese nombre'}), 400
        
        # Crear sucursal con datos mínimos
        nuevo_id = get_next_id()
        nueva_sucursal = Sucursales(
            id_sucursal=nuevo_id,
            nombre=nombre.title(),
            direccion='Por definir',
            telefono='+504 0000-0000',
            email=f'sucursal{nuevo_id}@temp.com',
            ciudad=ciudad.title(),
            departamento='Por definir',
            codigo_postal='00000',
            activo=1,
            observaciones='Creada desde modal - completar información'
        )
        
        db.session.add(nueva_sucursal)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id_sucursal': nuevo_id,
            'nombre': nombre,
            'message': 'Sucursal creada exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

# READ - Listar todas las sucursales
@sucursales_bp.route('/')
@login_required
def listar():
    sucursales = db.session.query(Sucursales).all()
    return render_template('sucursales/listar.html', sucursales=sucursales)

# CREATE - Mostrar formulario de creación
@sucursales_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def crear():
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            direccion = request.form.get('direccion', '').strip()
            telefono = request.form.get('telefono', '').strip()
            email = request.form.get('email', '').strip().lower()
            ciudad = request.form.get('ciudad', '').strip()
            departamento = request.form.get('departamento', '').strip()
            codigo_postal = request.form.get('codigo_postal', '').strip()
            observaciones = request.form.get('observaciones', '').strip()
            
            # Validaciones
            valido, error = validar_nombre(nombre)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            valido, error = validar_direccion(direccion)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            # Verificar email duplicado
            email_existe = db.session.query(Sucursales).filter(
                func.lower(Sucursales.email) == email
            ).first()
            if email_existe:
                flash('Este email ya está registrado.', 'error')
                return render_template('sucursales/form.html')
            
            valido, error = validar_ciudad(ciudad)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            valido, error = validar_departamento(departamento)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            valido, error = validar_codigo_postal(codigo_postal)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html')
            
            if observaciones:
                valido, error = validar_observaciones(observaciones)
                if not valido:
                    flash(error, 'error')
                    return render_template('sucursales/form.html')
            
            # Validar nombre único
            existe = db.session.query(Sucursales).filter_by(nombre=nombre).first()
            if existe:
                flash('Ya existe una sucursal con ese nombre.', 'error')
                return render_template('sucursales/form.html')
            
            # Crear sucursal
            nuevo_id = get_next_id()
            nueva_sucursal = Sucursales(
                id_sucursal=nuevo_id,
                nombre=nombre.title(),
                direccion=direccion,
                telefono=telefono,
                email=email,
                ciudad=ciudad.title(),
                departamento=departamento.title(),
                codigo_postal=codigo_postal,
                activo=int(request.form.get('activo', 1)),
                observaciones=observaciones or None
            )
            
            db.session.add(nueva_sucursal)
            db.session.commit()
            
            flash(f'Sucursal {nombre} creada exitosamente.', 'success')
            return redirect(url_for('sucursales.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear sucursal: {str(e)}', 'error')
    
    return render_template('sucursales/form.html', sucursal=None)

# UPDATE - Mostrar formulario de edición
@sucursales_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    sucursal = db.session.get(Sucursales, id)
    if not sucursal:
        flash('Sucursal no encontrada.', 'error')
        return redirect(url_for('sucursales.listar'))
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            direccion = request.form.get('direccion', '').strip()
            telefono = request.form.get('telefono', '').strip()
            email = request.form.get('email', '').strip().lower()
            ciudad = request.form.get('ciudad', '').strip()
            departamento = request.form.get('departamento', '').strip()
            codigo_postal = request.form.get('codigo_postal', '').strip()
            observaciones = request.form.get('observaciones', '').strip()
            
            # Validaciones
            valido, error = validar_nombre(nombre)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            valido, error = validar_direccion(direccion)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            # Verificar email duplicado (excepto el actual)
            email_existe = db.session.query(Sucursales).filter(
                func.lower(Sucursales.email) == email,
                Sucursales.id_sucursal != id
            ).first()
            if email_existe:
                flash('Este email ya está registrado.', 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            valido, error = validar_ciudad(ciudad)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            valido, error = validar_departamento(departamento)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            valido, error = validar_codigo_postal(codigo_postal)
            if not valido:
                flash(error, 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            if observaciones:
                valido, error = validar_observaciones(observaciones)
                if not valido:
                    flash(error, 'error')
                    return render_template('sucursales/form.html', sucursal=sucursal)
            
            # Validar nombre único (excepto el actual)
            existe = db.session.query(Sucursales).filter(
                Sucursales.nombre == nombre,
                Sucursales.id_sucursal != id
            ).first()
            if existe:
                flash('Ya existe una sucursal con ese nombre.', 'error')
                return render_template('sucursales/form.html', sucursal=sucursal)
            
            # Actualizar datos
            sucursal.nombre = nombre.title()
            sucursal.direccion = direccion
            sucursal.telefono = telefono
            sucursal.email = email
            sucursal.ciudad = ciudad.title()
            sucursal.departamento = departamento.title()
            sucursal.codigo_postal = codigo_postal
            sucursal.activo = int(request.form.get('activo', 1))
            sucursal.observaciones = observaciones or None
            
            db.session.commit()
            flash(f'Sucursal {nombre} actualizada exitosamente.', 'success')
            return redirect(url_for('sucursales.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar sucursal: {str(e)}', 'error')
    
    return render_template('sucursales/form.html', sucursal=sucursal)

# DELETE - Eliminar sucursal
@sucursales_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    try:
        sucursal = db.session.get(Sucursales, id)
        if not sucursal:
            flash('Sucursal no encontrada.', 'error')
            return redirect(url_for('sucursales.listar'))
        
        # Verificar si tiene relaciones
        if sucursal.Empleados or sucursal.Inventarios or sucursal.Facturas_Sar:
            flash(f'No se puede eliminar la sucursal "{sucursal.nombre}" porque tiene registros asociados (empleados, inventarios o facturas).', 'error')
            return redirect(url_for('sucursales.listar'))
        
        nombre = sucursal.nombre
        db.session.delete(sucursal)
        db.session.commit()
        flash(f'Sucursal {nombre} eliminada exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar sucursal: {str(e)}', 'error')
    
    return redirect(url_for('sucursales.listar'))