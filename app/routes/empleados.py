from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required, current_user
from app import db
from models import Empleados, Sucursales, Pais, EmpleadosDocumento, TiposDocumentos
from datetime import date, datetime
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
import re
import secrets
import string
from decimal import Decimal
from utils import hash_password

bp = Blueprint('empleados', __name__, url_prefix='/empleados')

# Roles predefinidos para empleados
ROLES_EMPLEADOS = [
    'Gerente',
    'Bibliotecario',
    'Asistente',
    'Cajero',
    'Soporte Técnico',
    'Recursos Humanos',
    'Administrador de Sistema'
]

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID disponible para Empleados"""
    max_id = db.session.execute(
        select(func.max(Empleados.id_empleado))
    ).scalar()
    return (max_id or 0) + 1

def get_next_documento_id():
    """Obtiene el siguiente ID disponible para EmpleadosDocumento"""
    max_id = db.session.execute(
        select(func.max(EmpleadosDocumento.id_empleado_documento))
    ).scalar()
    return (max_id or 0) + 1

def validar_solo_letras(texto, campo):
    """Validar que un campo solo contenga letras y espacios"""
    if not texto or not texto.strip():
        return False, f'{campo} es obligatorio'
    
    texto_limpio = ' '.join(texto.split())
    
    if not re.match(r'^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]+$', texto_limpio):
        return False, f'{campo} solo puede contener letras y espacios'
    
    if '  ' in texto:
        return False, f'{campo} no puede tener más de 1 espacio consecutivo'
    
    if re.search(r'([A-Za-zÁÉÍÓÚáéíóúÑñ])\1{2,}', texto_limpio):
        return False, f'{campo} no puede tener la misma letra repetida más de 2 veces seguidas'
    
    if len(texto_limpio) < 2:
        return False, f'{campo} debe tener al menos 2 caracteres'
    if len(texto_limpio) > 100:
        return False, f'{campo} no puede exceder 100 caracteres'
    
    return True, None

def validar_usuario(usuario, id_actual=None):
    """Validar nombre de usuario"""
    if not usuario or not usuario.strip():
        return False, 'El usuario es obligatorio'
    
    usuario = usuario.strip().lower()
    
    if len(usuario) < 2:
        return False, 'El usuario debe tener al menos 2 caracteres'
    
    if len(usuario) > 50:
        return False, 'El usuario no puede exceder 50 caracteres'
    
    if not re.match(r'^[a-z0-9._-]+$', usuario):
        return False, 'El usuario solo puede contener letras minúsculas, números, puntos, guiones y guión bajo'
    
    # Verificar duplicados
    query = select(Empleados).where(func.lower(Empleados.usuario) == usuario)
    if id_actual:
        query = query.where(Empleados.id_empleado != id_actual)
    
    existe = db.session.execute(query).scalar_one_or_none()
    if existe:
        return False, 'Este nombre de usuario ya está en uso'
    
    return True, None

def validar_email(email, id_actual=None):
    """Validar formato de email"""
    if not email or not email.strip():
        return False, 'Email es obligatorio'
    
    email = email.strip().lower()
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, 'Formato de email inválido'
    
    if len(email) > 100:
        return False, 'Email no puede exceder 100 caracteres'
    
    # Verificar duplicados
    query = select(Empleados).where(func.lower(Empleados.email) == email)
    if id_actual:
        query = query.where(Empleados.id_empleado != id_actual)
    
    existe = db.session.execute(query).scalar_one_or_none()
    if existe:
        return False, 'Este email ya está registrado'
    
    return True, None

def validar_telefono(telefono):
    """Validar formato de teléfono hondureño"""
    if not telefono:
        return True, None
    
    telefono_limpio = telefono.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    
    if telefono_limpio.startswith('+504'):
        numero = telefono_limpio[4:]
    elif telefono_limpio.startswith('504'):
        numero = telefono_limpio[3:]
    else:
        numero = telefono_limpio
    
    if not numero.isdigit():
        return False, 'El teléfono solo puede contener números'
    
    if len(numero) != 8:
        return False, 'El número debe tener 8 dígitos'
    
    if numero[0] not in ['3', '7', '8', '9']:
        return False, 'El número debe empezar con 3, 7, 8 o 9'
    
    if not telefono_limpio.startswith('+504'):
        return False, 'El teléfono debe incluir +504'
    
    return True, None

def validar_salario(salario_str):
    """Validar salario"""
    try:
        salario = Decimal(salario_str)
        
        if salario < 0:
            return False, 'El salario no puede ser negativo'
        
        if salario > 99999999.99:
            return False, 'El salario no puede exceder 99,999,999.99'
        
        return True, None
    except:
        return False, 'Formato de salario inválido'

def validar_valor_documento(valor, tipo_documento_nombre):
    """
    Valida el formato del documento según el tipo
    Retorna (es_valido, mensaje_error)
    """
    valor = valor.strip()
    
    if not valor:
        return False, "El valor del documento no puede estar vacío"
    
    tipo_lower = tipo_documento_nombre.lower()
    
    if 'identidad' in tipo_lower or 'dni' in tipo_lower:
        if not re.match(r'^\d{4}-\d{4}-\d{5}$', valor):
            return False, "Formato inválido. Debe ser: 0000-0000-00000 (13 dígitos)"
    
    elif 'rtn' in tipo_lower:
        if not re.match(r'^\d{4}-\d{4}-\d{6}$', valor):
            return False, "Formato inválido. Debe ser: 0000-0000-000000 (14 dígitos)"
    
    elif 'pasaporte' in tipo_lower:
        if not re.match(r'^[A-Z0-9]{6,9}$', valor.upper()):
            return False, "Formato inválido. Debe tener 6-9 caracteres alfanuméricos (sin espacios)"
    
    elif 'licencia' in tipo_lower:
        if not re.match(r'^[A-Z]{0,2}\d{6,10}$', valor.upper()):
            return False, "Formato inválido. Ej: HN123456 o 12345678"
    
    else:
        if len(valor) < 3:
            return False, "El documento debe tener al menos 3 caracteres"
        if len(valor) > 50:
            return False, "El documento no puede exceder 50 caracteres"
    
    return True, None

def validar_duplicado_documento(id_empleado, id_tipo_documento, valor_documento, id_actual=None):
    """
    Verifica si ya existe un documento con el mismo valor para el mismo empleado y tipo
    """
    query = select(EmpleadosDocumento).where(
        EmpleadosDocumento.id_empleado == id_empleado,
        EmpleadosDocumento.id_tipo_documento == id_tipo_documento,
        EmpleadosDocumento.valor_documento == valor_documento
    )
    
    if id_actual:
        query = query.where(EmpleadosDocumento.id_empleado_documento != id_actual)
    
    existe = db.session.execute(query).scalar_one_or_none()
    return existe is not None

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los empleados"""
    empleados = db.session.execute(
        select(Empleados, Sucursales, Pais)
        .join(Sucursales, Empleados.id_sucursal == Sucursales.id_sucursal)
        .join(Pais, Empleados.id_pais == Pais.id_pais)
        .order_by(Empleados.nombres)
    ).all()
    
    return render_template('empleados/listar.html', empleados=empleados)

@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def crear():
    """Crea un nuevo empleado"""
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == True).order_by(Sucursales.nombre)
    ).scalars().all()
    
    paises = db.session.execute(
        select(Pais).order_by(Pais.nombre_pais)
    ).scalars().all()
    
    tipos_documentos = db.session.execute(
        select(TiposDocumentos).where(TiposDocumentos.activo == True).order_by(TiposDocumentos.nombre)
    ).scalars().all()
    
    if request.method == 'POST':
        try:
            nombres = request.form.get('nombres', '').strip()
            apellidos = request.form.get('apellidos', '').strip()
            usuario = request.form.get('usuario', '').strip().lower()
            email = request.form.get('email', '').strip().lower()
            telefono = request.form.get('telefono', '').strip()
            id_sucursal = int(request.form.get('id_sucursal'))
            id_pais = int(request.form.get('id_pais'))
            rol = request.form.get('rol', '')
            salario_str = request.form.get('salario', '0')
            observaciones = request.form.get('observaciones', '').strip()
            
            # Validaciones
            valido, error = validar_solo_letras(nombres, 'Nombres')
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            valido, error = validar_solo_letras(apellidos, 'Apellidos')
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            valido, error = validar_usuario(usuario)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            if rol not in ROLES_EMPLEADOS:
                flash('Rol inválido', 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            valido, error = validar_salario(salario_str)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', sucursales=sucursales, paises=paises, 
                                     roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos)
            
            # Generar contraseña temporal
            chars = string.ascii_letters + string.digits + '!@#$%'
            temp_password = ''.join(secrets.choice(chars) for _ in range(10))
            
            # Crear empleado
            nuevo_empleado = Empleados(
                id_empleado=get_next_id(),
                nombres=nombres.title(),
                apellidos=apellidos.title(),
                usuario=usuario,
                email=email,
                password_hash=hash_password(temp_password),
                telefono=telefono,
                id_sucursal=id_sucursal,
                id_pais=id_pais,
                rol=rol,
                fecha_contratacion=date.today(),
                salario=Decimal(salario_str),
                activo=1,
                observaciones=observaciones or None
            )
            
            db.session.add(nuevo_empleado)
            db.session.commit()
            
            flash(f'✅ Empleado {nombres} {apellidos} creado. Usuario: {usuario}, Contraseña: {temp_password}', 'success')
            return redirect(url_for('empleados.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear empleado: {str(e)}', 'error')
    
    return render_template('empleados/form.html', 
                         sucursales=sucursales, 
                         paises=paises,
                         roles=ROLES_EMPLEADOS,
                         tipos_documentos=tipos_documentos)

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edita un empleado existente"""
    empleado = db.session.get(Empleados, id)
    
    if not empleado:
        flash('Empleado no encontrado', 'error')
        return redirect(url_for('empleados.listar'))
    
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == True).order_by(Sucursales.nombre)
    ).scalars().all()
    
    paises = db.session.execute(
        select(Pais).order_by(Pais.nombre_pais)
    ).scalars().all()
    
    tipos_documentos = db.session.execute(
        select(TiposDocumentos).where(TiposDocumentos.activo == True).order_by(TiposDocumentos.nombre)
    ).scalars().all()
    
    # Get existing documents for this employee
    documentos_empleado = db.session.execute(
        select(EmpleadosDocumento, TiposDocumentos)
        .join(TiposDocumentos, EmpleadosDocumento.id_tipo_documento == TiposDocumentos.id_tipo_documento)
        .where(EmpleadosDocumento.id_empleado == id)
        .order_by(TiposDocumentos.nombre)
    ).all()
    
    if request.method == 'POST':
        try:
            nombres = request.form.get('nombres', '').strip()
            apellidos = request.form.get('apellidos', '').strip()
            usuario = request.form.get('usuario', '').strip().lower()
            email = request.form.get('email', '').strip().lower()
            telefono = request.form.get('telefono', '').strip()
            id_sucursal = int(request.form.get('id_sucursal'))
            id_pais = int(request.form.get('id_pais'))
            rol = request.form.get('rol', '')
            salario_str = request.form.get('salario', '0')
            activo = request.form.get('activo') == 'on'
            observaciones = request.form.get('observaciones', '').strip()
            
            # Validaciones (similar a crear, pero con id_actual)
            valido, error = validar_solo_letras(nombres, 'Nombres')
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                     paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                     documentos_empleado=documentos_empleado)
            
            valido, error = validar_solo_letras(apellidos, 'Apellidos')
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                     paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                     documentos_empleado=documentos_empleado)
            
            valido, error = validar_usuario(usuario, id)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                     paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                     documentos_empleado=documentos_empleado)
            
            valido, error = validar_email(email, id)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                     paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                     documentos_empleado=documentos_empleado)
            
            valido, error = validar_salario(salario_str)
            if not valido:
                flash(error, 'error')
                return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                     paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                     documentos_empleado=documentos_empleado)
            
            # Procesar nuevos documentos si existen
            nuevos_documentos = []
            if 'nuevo_tipo_documento' in request.form and 'nuevo_valor_documento' in request.form:
                tipos = request.form.getlist('nuevo_tipo_documento')
                valores = request.form.getlist('nuevo_valor_documento')
                
                for tipo_id, valor in zip(tipos, valores):
                    if tipo_id and valor:
                        tipo_id = int(tipo_id)
                        valor = valor.strip().upper()
                        
                        # Obtener el tipo de documento para validación
                        tipo_doc = db.session.get(TiposDocumentos, tipo_id)
                        if not tipo_doc:
                            flash(f'Tipo de documento no encontrado', 'error')
                            return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                                 paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                                 documentos_empleado=documentos_empleado)
                        
                        # Validar formato del documento
                        es_valido, mensaje_error = validar_valor_documento(valor, tipo_doc.nombre)
                        if not es_valido:
                            flash(mensaje_error, 'error')
                            return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                                 paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                                 documentos_empleado=documentos_empleado)
                        
                        # Validar duplicados
                        if validar_duplicado_documento(id, tipo_id, valor):
                            flash(f'El empleado ya tiene un documento de tipo "{tipo_doc.nombre}" con el mismo valor', 'error')
                            return render_template('empleados/form.html', empleado=empleado, sucursales=sucursales, 
                                                 paises=paises, roles=ROLES_EMPLEADOS, tipos_documentos=tipos_documentos,
                                                 documentos_empleado=documentos_empleado)
                        
                        nuevos_documentos.append({
                            'id_tipo_documento': tipo_id,
                            'valor_documento': valor
                        })
            
            # Actualizar
            empleado.nombres = nombres.title()
            empleado.apellidos = apellidos.title()
            empleado.usuario = usuario
            empleado.email = email
            empleado.telefono = telefono
            empleado.id_sucursal = id_sucursal
            empleado.id_pais = id_pais
            empleado.rol = rol
            empleado.salario = Decimal(salario_str)
            empleado.activo = 1 if activo else 0
            empleado.observaciones = observaciones or None
            
            # Agregar nuevos documentos
            for doc_data in nuevos_documentos:
                nuevo_doc = EmpleadosDocumento(
                    id_empleado_documento=get_next_documento_id(),
                    id_empleado=id,
                    id_tipo_documento=doc_data['id_tipo_documento'],
                    valor_documento=doc_data['valor_documento']
                )
                db.session.add(nuevo_doc)
            
            db.session.commit()
            
            mensaje = f'✅ Empleado {nombres} {apellidos} actualizado'
            if nuevos_documentos:
                mensaje += f'. Se agregaron {len(nuevos_documentos)} documento(s)'
            
            flash(mensaje, 'success')
            return redirect(url_for('empleados.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar empleado: {str(e)}', 'error')
    
    return render_template('empleados/form.html', 
                         empleado=empleado,
                         sucursales=sucursales, 
                         paises=paises,
                         roles=ROLES_EMPLEADOS,
                         tipos_documentos=tipos_documentos,
                         documentos_empleado=documentos_empleado)

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Elimina un empleado"""
    try:
        empleado = db.session.get(Empleados, id)
        
        if not empleado:
            flash('Empleado no encontrado', 'error')
            return redirect(url_for('empleados.listar'))
        
        nombre_completo = f'{empleado.nombres} {empleado.apellidos}'
        db.session.delete(empleado)
        db.session.commit()
        
        flash(f'✅ Empleado {nombre_completo} eliminado', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar empleado: {str(e)}', 'error')
    
    return redirect(url_for('empleados.listar'))

@bp.route('/resetear-password/<int:id>', methods=['POST'])
@login_required
def resetear_password(id):
    """Resetea la contraseña de un empleado"""
    try:
        empleado = db.session.get(Empleados, id)
        
        if not empleado:
            flash('Empleado no encontrado', 'error')
            return redirect(url_for('empleados.listar'))
        
        # Generar nueva contraseña
        chars = string.ascii_letters + string.digits + '!@#$%'
        temp_password = ''.join(secrets.choice(chars) for _ in range(10))
        
        empleado.password_hash = hash_password(temp_password)
        db.session.commit()
        
        flash(f'✅ Nueva contraseña para {empleado.nombres}: {temp_password}', 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al resetear contraseña: {str(e)}', 'error')
    
    return redirect(url_for('empleados.editar', id=id))

# ================== DOCUMENT MANAGEMENT ROUTES ==================

@bp.route('/eliminar-documento/<int:id>', methods=['POST'])
@login_required
def eliminar_documento(id):
    """API endpoint to delete an employee document"""
    try:
        documento = db.session.get(EmpleadosDocumento, id)
        if not documento:
            return jsonify({'success': False, 'message': 'Documento no encontrado'}), 404
        
        db.session.delete(documento)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Documento eliminado exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/documentos/<int:id>', methods=['GET'])
@login_required
def obtener_documentos(id):
    """API endpoint to get employee documents"""
    try:
        # Get documents for the employee
        documentos = db.session.execute(
            select(EmpleadosDocumento, TiposDocumentos)
            .join(TiposDocumentos, EmpleadosDocumento.id_tipo_documento == TiposDocumentos.id_tipo_documento)
            .where(EmpleadosDocumento.id_empleado == id)
            .order_by(TiposDocumentos.nombre)
        ).all()
        
        # Format documents for JSON response
        docs_list = []
        for documento, tipo_doc in documentos:
            docs_list.append({
                'id': documento.id_empleado_documento,
                'tipo_documento': tipo_doc.nombre,
                'valor_documento': documento.valor_documento
            })
        
        return jsonify({
            'success': True,
            'documentos': docs_list
        })
        
    except Exception as e:
        print(f"Error getting documents: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500