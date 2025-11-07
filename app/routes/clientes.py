from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from models import Clientes, EstadoUsuarios, ClientesDocumento, TiposDocumentos
from bcrypt import hashpw, gensalt
from datetime import datetime
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload
import re
import secrets
import string
import hmac
import hashlib

clientes_bp = Blueprint('clientes', __name__, url_prefix='/clientes')

def hash_password(password):
    """
    Hash de contraseña completamente aleatorio y único:
    1. Genera una sal aleatoria única de 32 bytes
    2. HMAC con pepper + sal
    3. Bcrypt
    4. Almacena: sal_aleatoria + hash (todo en hex)
    Resultado: Cada hash comienza diferente
    """
    # Obtener pepper desde configuración
    try:
        pepper = current_app.config.get('PEPPER_SECRET', '')
    except RuntimeError:
        from config import Config
        pepper = Config.PEPPER_SECRET
    
    # Generar sal aleatoria única de 32 bytes
    random_salt = secrets.token_bytes(32)
    
    # HMAC con pepper + sal aleatoria
    hmac_hash = hmac.new(
        (pepper + random_salt.hex()).encode('utf-8'),
        password.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    # Bcrypt sobre el HMAC
    bcrypt_hash = hashpw(hmac_hash, gensalt(rounds=12))
    
    # Combinar: sal_aleatoria + bcrypt_hash, todo en hexadecimal
    # La sal aleatoria va primero (64 caracteres hex = 32 bytes)
    final_hash = random_salt.hex() + bcrypt_hash.hex()
    
    return final_hash

def validar_solo_letras(texto, campo):
    """Validar que un campo solo contenga letras y espacios con reglas estrictas"""
    if not texto or not texto.strip():
        return False, f'{campo} es obligatorio'
    
    # Eliminar espacios múltiples para validación
    texto_limpio = ' '.join(texto.split())
    
    # Solo letras y espacios
    if not re.match(r'^[A-Za-zÁÉÍÓÚáéíóúÑñ\s]+$', texto_limpio):
        return False, f'{campo} solo puede contener letras y espacios'
    
    # No más de 1 espacio seguido en el texto original
    if '  ' in texto:  # 2 espacios
        return False, f'{campo} no puede tener más de 1 espacio consecutivo'
    
    # No más de 2 letras iguales seguidas (no existe en español)
    if re.search(r'([A-Za-zÁÉÍÓÚáéíóúÑñ])\1{2,}', texto_limpio):
        return False, f'{campo} no puede tener la misma letra repetida más de 2 veces seguidas'
    
    # Longitud
    if len(texto_limpio) < 2:
        return False, f'{campo} debe tener al menos 2 caracteres'
    if len(texto_limpio) > 50:
        return False, f'{campo} no puede exceder 50 caracteres'
    
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

def validar_direccion(direccion):
    """Validar dirección con límites de caracteres"""
    if not direccion or direccion == 'No especificada':
        return True, None
    
    direccion = direccion.strip()
    
    # No más de 1 espacio consecutivo
    if '  ' in direccion:
        return False, 'La dirección no puede tener más de 1 espacio consecutivo'
    
    # No más de 2 caracteres iguales seguidos (excepto espacios)
    if re.search(r'([^\s])\1{2,}', direccion):
        return False, 'La dirección no puede tener el mismo carácter repetido más de 2 veces seguidas'
    
    # Longitud máxima
    if len(direccion) > 200:
        return False, 'La dirección no puede exceder 200 caracteres'
    
    # Mínimo 5 caracteres
    if len(direccion) < 5:
        return False, 'La dirección debe tener al menos 5 caracteres'
    
    return True, None

def validar_observaciones(observaciones):
    """Validar observaciones con límites"""
    if not observaciones:
        return True, None
    
    observaciones = observaciones.strip()
    
    # No más de 1 espacio consecutivo
    if '  ' in observaciones:
        return False, 'Las observaciones no pueden tener más de 1 espacio consecutivo'
    
    # Longitud máxima
    if len(observaciones) > 500:
        return False, 'Las observaciones no pueden exceder 500 caracteres'
    
    return True, None

def validar_valor_documento(valor, tipo_documento_nombre):
    """
    Valida el formato del documento según el tipo
    Retorna (es_valido, mensaje_error)
    """
    valor = valor.strip()
    
    # Validar que no esté vacío
    if not valor:
        return False, "El valor del documento no puede estar vacío"
    
    # Validación según tipo de documento
    tipo_lower = tipo_documento_nombre.lower()
    
    if 'identidad' in tipo_lower or 'dni' in tipo_lower:
        # Formato: 0000-0000-00000 (13 dígitos + 2 guiones)
        if not re.match(r'^\d{4}-\d{4}-\d{5}$', valor):
            return False, "Formato inválido. Debe ser: 0000-0000-00000 (13 dígitos)"
    
    elif 'rtn' in tipo_lower:
        # Formato RTN: 0000-0000-000000 (14 dígitos + 2 guiones)
        if not re.match(r'^\d{4}-\d{4}-\d{6}$', valor):
            return False, "Formato inválido. Debe ser: 0000-0000-000000 (14 dígitos)"
    
    elif 'pasaporte' in tipo_lower:
        # Formato pasaporte: letras y números, 6-9 caracteres
        if not re.match(r'^[A-Z0-9]{6,9}$', valor.upper()):
            return False, "Formato inválido. Debe tener 6-9 caracteres alfanuméricos (sin espacios)"
    
    elif 'licencia' in tipo_lower:
        # Formato licencia: Letras opcionales + números
        if not re.match(r'^[A-Z]{0,2}\d{6,10}$', valor.upper()):
            return False, "Formato inválido. Ej: HN123456 o 12345678"
    
    else:
        # Para otros tipos: mínimo 3 caracteres, máximo 50
        if len(valor) < 3:
            return False, "El documento debe tener al menos 3 caracteres"
        if len(valor) > 50:
            return False, "El documento no puede exceder 50 caracteres"
    
    return True, None

def validar_duplicado_documento(id_cliente, id_tipo_documento, valor_documento, id_actual=None):
    """
    Verifica si ya existe un documento con el mismo valor para el mismo cliente y tipo
    """
    query = select(ClientesDocumento).where(
        ClientesDocumento.id_cliente == id_cliente,
        ClientesDocumento.id_tipo_documento == id_tipo_documento,
        ClientesDocumento.valor_documento == valor_documento
    )
    
    # Si estamos editando, excluir el registro actual
    if id_actual:
        query = query.where(ClientesDocumento.id_cliente_documento != id_actual)
    
    existe = db.session.execute(query).scalar_one_or_none()
    return existe is not None

def get_next_id():
    """Obtener el siguiente ID disponible para clientes"""
    ultimo_id = db.session.query(func.max(Clientes.id_cliente)).scalar()
    return (ultimo_id or 0) + 1

def get_next_documento_id():
    """Obtiene el siguiente ID disponible para ClientesDocumento"""
    max_id = db.session.execute(
        select(func.max(ClientesDocumento.id_cliente_documento))
    ).scalar()
    return (max_id or 0) + 1

# READ - Listar todos los clientes
@clientes_bp.route('/')
@login_required
def listar():
    # Use joinedload to eagerly load the Estado_Usuarios relationship
    clientes = db.session.query(Clientes).options(
        joinedload(Clientes.Estado_Usuarios)
    ).order_by(Clientes.fecha_registro.desc()).all()
    
    # Create a dictionary of estados for easy lookup
    estados = db.session.query(EstadoUsuarios).all()
    estados_dict = {estado.id_estado: estado for estado in estados}
    
    return render_template('clientes/listar.html', clientes=clientes, estados_dict=estados_dict)

# CREATE - Mostrar formulario de creación
@clientes_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def crear():
    estados = db.session.query(EstadoUsuarios).all()
    tipos_documentos = db.session.execute(
        select(TiposDocumentos).where(TiposDocumentos.activo == True).order_by(TiposDocumentos.nombre)
    ).scalars().all()
    
    if request.method == 'POST':
        try:
            nombres = request.form.get('nombres', '').strip()
            apellidos = request.form.get('apellidos', '').strip()
            email = request.form.get('email', '').strip().lower()
            telefono = request.form.get('telefono', '').strip()
            direccion = request.form.get('direccion', '').strip()
            observaciones = request.form.get('observaciones', '').strip()
            
            # Validar nombres
            valido, error = validar_solo_letras(nombres, 'Nombres')
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Validar apellidos
            valido, error = validar_solo_letras(apellidos, 'Apellidos')
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Validar email
            valido, error = validar_email(email)
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Verificar email duplicado
            email_existe = db.session.query(Clientes).filter(
                func.lower(Clientes.email) == email
            ).first()
            if email_existe:
                flash('Este email ya está registrado.', 'error')
                return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Validar teléfono
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Validar dirección
            if direccion:
                valido, error = validar_direccion(direccion)
                if not valido:
                    flash(error, 'error')
                    return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Validar observaciones
            if observaciones:
                valido, error = validar_observaciones(observaciones)
                if not valido:
                    flash(error, 'error')
                    return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)
            
            # Generar contraseña temporal automáticamente (más segura)
            # Incluye mayúsculas, minúsculas, dígitos y símbolos
            chars = string.ascii_letters + string.digits + '!@#$%'
            temp_password = ''.join(secrets.choice(chars) for _ in range(10))
            
            # Crear cliente con el método de hash personalizado
            nuevo_id = get_next_id()
            password_hash = hash_password(temp_password)
            
            nuevo_cliente = Clientes(
                id_cliente=nuevo_id,
                nombres=nombres.title(),
                apellidos=apellidos.title(),
                email=email,
                password_hash=password_hash,
                telefono=telefono if telefono else 'No especificado',
                direccion=direccion or 'No especificada',
                tipo_usuario=request.form.get('tipo_usuario', 'cliente'),
                fecha_registro=datetime.now(),
                id_estado=int(request.form.get('id_estado', 1)),
                ot=int(request.form.get('ot', 0)),
                observaciones=observaciones or None
            )
            
            db.session.add(nuevo_cliente)
            db.session.commit()
            
            flash(f'Cliente {nombres} {apellidos} creado exitosamente. Contraseña temporal: {temp_password} (Comparte esta contraseña con el usuario)', 'success')
            return redirect(url_for('clientes.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear cliente: {str(e)}', 'error')
            print(f"Error en crear cliente: {str(e)}")
    
    return render_template('clientes/form.html', cliente=None, estados=estados, tipos_documentos=tipos_documentos)

# UPDATE - Mostrar formulario de edición
@clientes_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    estados = db.session.query(EstadoUsuarios).all()
    tipos_documentos = db.session.execute(
        select(TiposDocumentos).where(TiposDocumentos.activo == True).order_by(TiposDocumentos.nombre)
    ).scalars().all()
    
    # Use joinedload to eagerly load the Estado_Usuarios relationship
    cliente = db.session.query(Clientes).options(
        joinedload(Clientes.Estado_Usuarios)
    ).filter(Clientes.id_cliente == id).first()
    
    if not cliente:
        flash('Cliente no encontrado.', 'error')
        return redirect(url_for('clientes.listar'))
    
    # Get existing documents for this client
    documentos_cliente = db.session.execute(
        select(ClientesDocumento, TiposDocumentos)
        .join(TiposDocumentos, ClientesDocumento.id_tipo_documento == TiposDocumentos.id_tipo_documento)
        .where(ClientesDocumento.id_cliente == id)
        .order_by(TiposDocumentos.nombre)
    ).all()
    
    if request.method == 'POST':
        try:
            nombres = request.form.get('nombres', '').strip()
            apellidos = request.form.get('apellidos', '').strip()
            telefono = request.form.get('telefono', '').strip()
            direccion = request.form.get('direccion', '').strip()
            observaciones = request.form.get('observaciones', '').strip()
            
            # Validar nombres
            valido, error = validar_solo_letras(nombres, 'Nombres')
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                     tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
            
            # Validar apellidos
            valido, error = validar_solo_letras(apellidos, 'Apellidos')
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                     tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
            
            # Validar teléfono
            valido, error = validar_telefono(telefono)
            if not valido:
                flash(error, 'error')
                return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                     tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
            
            # Validar dirección
            if direccion:
                valido, error = validar_direccion(direccion)
                if not valido:
                    flash(error, 'error')
                    return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                         tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
            
            # Validar observaciones
            if observaciones:
                valido, error = validar_observaciones(observaciones)
                if not valido:
                    flash(error, 'error')
                    return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                         tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
            
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
                            return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                                 tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
                        
                        # Validar formato del documento
                        es_valido, mensaje_error = validar_valor_documento(valor, tipo_doc.nombre)
                        if not es_valido:
                            flash(mensaje_error, 'error')
                            return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                                 tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
                        
                        # Validar duplicados
                        if validar_duplicado_documento(id, tipo_id, valor):
                            flash(f'El cliente ya tiene un documento de tipo "{tipo_doc.nombre}" con el mismo valor', 'error')
                            return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                                                 tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)
                        
                        nuevos_documentos.append({
                            'id_tipo_documento': tipo_id,
                            'valor_documento': valor
                        })
            
            # Actualizar datos del cliente
            cliente.nombres = nombres.title()
            cliente.apellidos = apellidos.title()
            cliente.telefono = telefono if telefono else 'No especificado'
            cliente.direccion = direccion or 'No especificada'
            cliente.tipo_usuario = request.form.get('tipo_usuario', 'cliente')
            cliente.id_estado = int(request.form.get('id_estado', 1))
            cliente.ot = int(request.form.get('ot', 0))
            cliente.observaciones = observaciones or None
            
            # Agregar nuevos documentos
            for doc_data in nuevos_documentos:
                nuevo_doc = ClientesDocumento(
                    id_cliente_documento=get_next_documento_id(),
                    id_cliente=id,
                    id_tipo_documento=doc_data['id_tipo_documento'],
                    valor_documento=doc_data['valor_documento']
                )
                db.session.add(nuevo_doc)
            
            db.session.commit()
            
            mensaje = f'Cliente {nombres} {apellidos} actualizado exitosamente.'
            if nuevos_documentos:
                mensaje += f' Se agregaron {len(nuevos_documentos)} documento(s).'
            
            flash(mensaje, 'success')
            return redirect(url_for('clientes.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar cliente: {str(e)}', 'error')
            print(f"Error en editar cliente: {str(e)}")
    
    return render_template('clientes/form.html', cliente=cliente, estados=estados, 
                         tipos_documentos=tipos_documentos, documentos_cliente=documentos_cliente)

# DELETE - Eliminar cliente
@clientes_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    try:
        cliente = db.session.get(Clientes, id)
        if not cliente:
            flash('Cliente no encontrado.', 'error')
            return redirect(url_for('clientes.listar'))
        
        # No permitir que el usuario se elimine a sí mismo
        if cliente.id_cliente == current_user.id_cliente:
            flash('No puedes eliminar tu propia cuenta.', 'error')
            return redirect(url_for('clientes.listar'))
        
        nombre_completo = f'{cliente.nombres} {cliente.apellidos}'
        db.session.delete(cliente)
        db.session.commit()
        flash(f'Cliente {nombre_completo} eliminado exitosamente.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar cliente: {str(e)}', 'error')
    
    return redirect(url_for('clientes.listar'))

# RESET PASSWORD
@clientes_bp.route('/resetear-password/<int:id>', methods=['POST'])
@login_required
def resetear_password(id):
    try:
        cliente = db.session.get(Clientes, id)
        if not cliente:
            flash('Cliente no encontrado.', 'error')
            return redirect(url_for('clientes.listar'))
        
        # Generate random password (más segura con caracteres especiales)
        chars = string.ascii_letters + string.digits + '!@#$%'
        temp_password = ''.join(secrets.choice(chars) for _ in range(10))
        
        # Hash the temporary password usando el método personalizado
        cliente.password_hash = hash_password(temp_password)
        
        # Optionally set estado to "Pendiente cambio de contraseña"
        # cliente.id_estado = 4
        
        db.session.commit()
        
        flash(f'Contraseña temporal para {cliente.nombres}: {temp_password} (Comparte esta contraseña con el usuario)', 'warning')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al resetear contraseña: {str(e)}', 'error')
        print(f"Error en resetear password: {str(e)}")
    
    return redirect(url_for('clientes.editar', id=id))

# API endpoint to delete a document (called from form)
@clientes_bp.route('/eliminar-documento/<int:id>', methods=['POST'])
@login_required
def eliminar_documento(id):
    try:
        documento = db.session.get(ClientesDocumento, id)
        if not documento:
            return jsonify({'success': False, 'message': 'Documento no encontrado'}), 404
        
        db.session.delete(documento)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Documento eliminado exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    

# Add this route to your clientes_bp in the routes file

@clientes_bp.route('/documentos/<int:id>', methods=['GET'])
@login_required
def obtener_documentos(id):
    """API endpoint to get client documents"""
    try:
        # Get documents for the client
        documentos = db.session.execute(
            select(ClientesDocumento, TiposDocumentos)
            .join(TiposDocumentos, ClientesDocumento.id_tipo_documento == TiposDocumentos.id_tipo_documento)
            .where(ClientesDocumento.id_cliente == id)
            .order_by(TiposDocumentos.nombre)
        ).all()
        
        # Format documents for JSON response
        docs_list = []
        for documento, tipo_doc in documentos:
            docs_list.append({
                'id': documento.id_cliente_documento,
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