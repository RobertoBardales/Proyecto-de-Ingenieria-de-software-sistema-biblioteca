from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from models import Clientes, Empleados
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import joinedload
import re

# Import shared password functions
from utils import hash_password, verify_password

auth = Blueprint('auth', __name__)

def validar_solo_letras(texto, campo_nombre):
    """Validar que el campo solo contenga letras y espacios con reglas estrictas"""
    if not texto or not texto.strip():
        return False, f'{campo_nombre} es obligatorio'
    
    # Eliminar espacios múltiples para validación
    texto_limpio = ' '.join(texto.split())
    
    # Longitud
    if len(texto_limpio) < 2:
        return False, f'{campo_nombre} debe tener al menos 2 caracteres'
    if len(texto_limpio) > 20:
        return False, f'{campo_nombre} no puede exceder 20 caracteres'
    
    # No más de 2 espacios seguidos en el texto original
    if '   ' in texto:  # 3 espacios
        return False, f'{campo_nombre} no puede tener más de 2 espacios consecutivos'
    
    # No más de 2 letras iguales seguidas
    if re.search(r'(.)\1{2,}', texto_limpio):
        return False, f'{campo_nombre} no puede tener la misma letra repetida más de 2 veces seguidas'
    
    # Solo letras (incluyendo acentos y ñ) y espacios
    if not re.match(r'^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]+$', texto_limpio):
        return False, f'{campo_nombre} solo puede contener letras y espacios'
    
    return True, None

def validar_password(password, confirmar=None):
    """Validar contraseña con requisitos estrictos"""
    if not password:
        return False, 'Contraseña es obligatoria'
    
    if len(password) < 8:
        return False, 'Contraseña debe tener al menos 8 caracteres'
    
    if len(password) > 100:
        return False, 'Contraseña no puede exceder 100 caracteres'
    
    # Verificar que tenga al menos una mayúscula
    if not re.search(r'[A-Z]', password):
        return False, 'Contraseña debe contener al menos una letra mayúscula'
    
    # Verificar que tenga al menos una minúscula
    if not re.search(r'[a-z]', password):
        return False, 'Contraseña debe contener al menos una letra minúscula'
    
    # Verificar que tenga al menos un número
    if not re.search(r'[0-9]', password):
        return False, 'Contraseña debe contener al menos un número'
    
    # Verificar que tenga al menos un carácter especial
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
        return False, 'Contraseña debe contener al menos un carácter especial'
    
    # Verificar que las contraseñas coincidan
    if confirmar is not None and password != confirmar:
        return False, 'Las contraseñas no coinciden'
    
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
    if not telefono or telefono == 'No especificado':
        return True, None
    
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

def get_next_id():
    """Obtener el siguiente ID disponible para clientes"""
    ultimo_id = db.session.query(func.max(Clientes.id_cliente)).scalar()
    return (ultimo_id or 0) + 1

@auth.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        email_or_username = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email_or_username or not password:
            flash('Por favor completa todos los campos.', 'error')
            return render_template('login.html')
        
        # Try to find user in both Clientes and Empleados
        usuario = None
        
        # First, try Clientes by email
        usuario = db.session.query(Clientes).filter(
            func.lower(Clientes.email) == email_or_username
        ).first()
        
        # If not found, try Empleados by email or username
        if not usuario:
            usuario = db.session.query(Empleados).filter(
                (func.lower(Empleados.email) == email_or_username) |
                (func.lower(Empleados.usuario) == email_or_username)
            ).first()
        
        # Verificar si existe y la contraseña es correcta
        if usuario and verify_password(password, usuario.password_hash):
            # Check if it's a Cliente with Estado_Usuarios
            if isinstance(usuario, Clientes):
                if hasattr(usuario, 'Estado_Usuarios') and usuario.Estado_Usuarios:
                    estado = usuario.Estado_Usuarios
                    
                    # Verificar si el estado permite login
                    if not estado.permite_login:
                        flash(f'Tu cuenta está {estado.nombre}. No puedes acceder al sistema.', 'error')
                        return render_template('login.html')
                    
                    # Si el estado es "Pendiente cambio de contraseña" (id_estado == 4)
                    if usuario.id_estado == 4:
                        flash('Debes cambiar tu contraseña antes de continuar.', 'warning')
                        return render_template('login.html')
            
            # Check if it's an Empleado with activo status
            elif isinstance(usuario, Empleados):
                if not usuario.activo:
                    flash('Tu cuenta de empleado está desactivada. Contacta al administrador.', 'error')
                    return render_template('login.html')
            
            # Login exitoso
            login_user(usuario)
            
            # Get display name based on user type
            nombre = usuario.nombres if hasattr(usuario, 'nombres') else usuario.usuario
            flash(f'¡Bienvenido, {nombre}!', 'success')
            
            # Redirect to next page if exists, otherwise to index
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.index'))
        else:
            flash('Email/Usuario o contraseña incorrectos.', 'error')
    
    return render_template('login.html')

@auth.route('/registrar', methods=['GET', 'POST'])
def registrar():
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        try:
            nombres = request.form.get('nombres', '').strip()
            apellidos = request.form.get('apellidos', '').strip()
            email = request.form.get('email', '').strip().lower()
            telefono = request.form.get('telefono', '').strip()
            password = request.form.get('password', '')
            password_confirm = request.form.get('password_confirm', '')
            
            # Validar nombres
            valido, error = validar_solo_letras(nombres, 'Nombres')
            if not valido:
                flash(error, 'error')
                return render_template('registrar.html')
            
            # Validar apellidos
            valido, error = validar_solo_letras(apellidos, 'Apellidos')
            if not valido:
                flash(error, 'error')
                return render_template('registrar.html')
            
            # Validar email
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('registrar.html')
            
            # Verificar si el email ya existe (case-insensitive)
            email_existe = db.session.query(Clientes).filter(
                func.lower(Clientes.email) == email
            ).first()
            
            if email_existe:
                flash('Este email ya está registrado.', 'error')
                return render_template('registrar.html')
            
            # Validar teléfono
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('registrar.html')
            
            # Validar contraseña
            valido, error = validar_password(password, password_confirm)
            if not valido:
                flash(error, 'error')
                return render_template('registrar.html')
            
            # Obtener siguiente ID
            nuevo_id = get_next_id()
            
            # Hash de la contraseña con método mejorado
            password_hash_value = hash_password(password)
            
            # Crear nuevo cliente
            nuevo_cliente = Clientes(
                id_cliente=nuevo_id,
                nombres=nombres.title(),
                apellidos=apellidos.title(),
                email=email,
                password_hash=password_hash_value,
                telefono=telefono if telefono else 'No especificado',
                direccion='No especificada',
                tipo_usuario='cliente',
                fecha_registro=datetime.now(),
                ot=0,
                id_estado=1,  # 1 = Activo
                observaciones=None
            )
            
            db.session.add(nuevo_cliente)
            db.session.commit()
            
            flash('¡Cuenta creada exitosamente! Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la cuenta: {str(e)}', 'error')
            print(f"Error en registro: {str(e)}")
    
    return render_template('registrar.html')

@auth.route('/logout')
@login_required
def logout():
    nombre = current_user.nombres if hasattr(current_user, 'nombres') else current_user.usuario
    logout_user()
    flash(f'Hasta pronto, {nombre}. Has cerrado sesión.', 'info')
    return redirect(url_for('main.index'))