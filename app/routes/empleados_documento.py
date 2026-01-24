from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import select, func
from models import EmpleadosDocumento, Empleados, TiposDocumentos
from app import db
from flask_login import login_required
import re

bp = Blueprint('empleados_documento', __name__, url_prefix='/empleados-documento')

# ================== FUNCIONES AUXILIARES ==================

def get_next_id():
    """Obtiene el siguiente ID disponible para EmpleadosDocumento"""
    max_id = db.session.execute(
        select(func.max(EmpleadosDocumento.id_empleado_documento))
    ).scalar()
    return (max_id or 0) + 1

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

def validar_duplicado(id_empleado, id_tipo_documento, valor_documento, id_actual=None):
    """
    Verifica si ya existe un documento con el mismo valor para el mismo empleado y tipo
    """
    query = select(EmpleadosDocumento).where(
        EmpleadosDocumento.id_empleado == id_empleado,
        EmpleadosDocumento.id_tipo_documento == id_tipo_documento,
        EmpleadosDocumento.valor_documento == valor_documento
    )
    
    # Si estamos editando, excluir el registro actual
    if id_actual:
        query = query.where(EmpleadosDocumento.id_empleado_documento != id_actual)
    
    existe = db.session.execute(query).scalar_one_or_none()
    return existe is not None

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    """Lista todos los documentos de empleados con joins"""
    documentos = db.session.execute(
        select(EmpleadosDocumento, Empleados, TiposDocumentos)
        .join(Empleados, EmpleadosDocumento.id_empleado == Empleados.id_empleado)
        .join(TiposDocumentos, EmpleadosDocumento.id_tipo_documento == TiposDocumentos.id_tipo_documento)
        .order_by(Empleados.nombres)
    ).all()
    
    return render_template('empleados_documento/listar.html', documentos=documentos)

@bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo():
    """Crea un nuevo documento para un empleado"""
    if request.method == 'POST':
        try:
            # Obtener datos del form
            id_empleado = int(request.form.get('id_empleado'))
            id_tipo_documento = int(request.form.get('id_tipo_documento'))
            valor_documento = request.form.get('valor_documento', '').strip().upper()
            
            # Obtener el tipo de documento para validación
            tipo_doc = db.session.get(TiposDocumentos, id_tipo_documento)
            if not tipo_doc:
                flash('Tipo de documento no encontrado', 'error')
                return redirect(url_for('empleados_documento.nuevo'))
            
            # Validar formato del documento
            es_valido, mensaje_error = validar_valor_documento(valor_documento, tipo_doc.nombre)
            if not es_valido:
                flash(mensaje_error, 'error')
                return redirect(url_for('empleados_documento.nuevo'))
            
            # Validar duplicados
            if validar_duplicado(id_empleado, id_tipo_documento, valor_documento):
                flash(f'Este empleado ya tiene un documento de tipo "{tipo_doc.nombre}" con el mismo valor', 'error')
                return redirect(url_for('empleados_documento.nuevo'))
            
            # Crear el documento
            nuevo_doc = EmpleadosDocumento(
                id_empleado_documento=get_next_id(),
                id_empleado=id_empleado,
                id_tipo_documento=id_tipo_documento,
                valor_documento=valor_documento
            )
            
            db.session.add(nuevo_doc)
            db.session.commit()
            
            empleado = db.session.get(Empleados, id_empleado)
            flash(f'✅ Documento agregado exitosamente a {empleado.nombres} {empleado.apellidos}', 'success')
            return redirect(url_for('empleados_documento.listar'))
            
        except ValueError as e:
            db.session.rollback()
            flash(f'Error en los datos ingresados: {str(e)}', 'error')
            return redirect(url_for('empleados_documento.nuevo'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear documento: {str(e)}', 'error')
            return redirect(url_for('empleados_documento.nuevo'))
    
    # GET: Mostrar formulario
    empleados = db.session.execute(
        select(Empleados).where(Empleados.activo == True).order_by(Empleados.nombres, Empleados.apellidos)
    ).scalars().all()
    
    tipos_documentos = db.session.execute(
        select(TiposDocumentos).where(TiposDocumentos.activo == True).order_by(TiposDocumentos.nombre)
    ).scalars().all()
    
    return render_template('empleados_documento/form.html', 
                         empleados=empleados, 
                         tipos_documentos=tipos_documentos)

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edita un documento existente"""
    documento = db.session.get(EmpleadosDocumento, id)
    if not documento:
        flash('Documento no encontrado', 'error')
        return redirect(url_for('empleados_documento.listar'))
    
    if request.method == 'POST':
        try:
            # Obtener datos
            id_empleado = int(request.form.get('id_empleado'))
            id_tipo_documento = int(request.form.get('id_tipo_documento'))
            valor_documento = request.form.get('valor_documento', '').strip().upper()
            
            # Obtener el tipo de documento
            tipo_doc = db.session.get(TiposDocumentos, id_tipo_documento)
            if not tipo_doc:
                flash('Tipo de documento no encontrado', 'error')
                return redirect(url_for('empleados_documento.editar', id=id))
            
            # Validar formato
            es_valido, mensaje_error = validar_valor_documento(valor_documento, tipo_doc.nombre)
            if not es_valido:
                flash(mensaje_error, 'error')
                return redirect(url_for('empleados_documento.editar', id=id))
            
            # Validar duplicados (excluyendo el actual)
            if validar_duplicado(id_empleado, id_tipo_documento, valor_documento, id):
                flash(f'Este empleado ya tiene un documento de tipo "{tipo_doc.nombre}" con el mismo valor', 'error')
                return redirect(url_for('empleados_documento.editar', id=id))
            
            # Actualizar
            documento.id_empleado = id_empleado
            documento.id_tipo_documento = id_tipo_documento
            documento.valor_documento = valor_documento
            
            db.session.commit()
            
            empleado = db.session.get(Empleados, id_empleado)
            flash(f'✅ Documento de {empleado.nombres} {empleado.apellidos} actualizado exitosamente', 'success')
            return redirect(url_for('empleados_documento.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar documento: {str(e)}', 'error')
            return redirect(url_for('empleados_documento.editar', id=id))
    
    # GET: Mostrar formulario con datos
    empleados = db.session.execute(
        select(Empleados).where(Empleados.activo == True).order_by(Empleados.nombres, Empleados.apellidos)
    ).scalars().all()
    
    tipos_documentos = db.session.execute(
        select(TiposDocumentos).where(TiposDocumentos.activo == True).order_by(TiposDocumentos.nombre)
    ).scalars().all()
    
    return render_template('empleados_documento/form.html', 
                         documento=documento,
                         empleados=empleados, 
                         tipos_documentos=tipos_documentos)

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Elimina un documento de empleado"""
    try:
        documento = db.session.get(EmpleadosDocumento, id)
        if not documento:
            flash('Documento no encontrado', 'error')
            return redirect(url_for('empleados_documento.listar'))
        
        empleado = db.session.get(Empleados, documento.id_empleado)
        tipo_doc = db.session.get(TiposDocumentos, documento.id_tipo_documento)
        
        db.session.delete(documento)
        db.session.commit()
        
        flash(f'✅ Documento "{tipo_doc.nombre}" de {empleado.nombres} {empleado.apellidos} eliminado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar documento: {str(e)}', 'error')
    
    return redirect(url_for('empleados_documento.listar'))

# ================== API PARA MODAL (CREAR DOCUMENTO DESDE EMPLEADO) ==================

@bp.route('/crear-rapido', methods=['POST'])
@login_required
def crear_rapido():
    """API para crear documento desde modal en otras vistas"""
    try:
        data = request.get_json()
        
        id_empleado = int(data.get('id_empleado'))
        id_tipo_documento = int(data.get('id_tipo_documento'))
        valor_documento = data.get('valor_documento', '').strip().upper()
        
        # Validar tipo de documento
        tipo_doc = db.session.get(TiposDocumentos, id_tipo_documento)
        if not tipo_doc:
            return jsonify({'success': False, 'message': 'Tipo de documento no encontrado'}), 400
        
        # Validar formato
        es_valido, mensaje_error = validar_valor_documento(valor_documento, tipo_doc.nombre)
        if not es_valido:
            return jsonify({'success': False, 'message': mensaje_error}), 400
        
        # Validar duplicados
        if validar_duplicado(id_empleado, id_tipo_documento, valor_documento):
            return jsonify({'success': False, 'message': 'Este documento ya existe para este empleado'}), 400
        
        # Crear documento
        nuevo_doc = EmpleadosDocumento(
            id_empleado_documento=get_next_id(),
            id_empleado=id_empleado,
            id_tipo_documento=id_tipo_documento,
            valor_documento=valor_documento
        )
        
        db.session.add(nuevo_doc)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Documento agregado exitosamente',
            'documento': {
                'id': nuevo_doc.id_empleado_documento,
                'tipo': tipo_doc.nombre,
                'valor': nuevo_doc.valor_documento
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# ================== API PARA OBTENER DOCUMENTOS DE UN EMPLEADO ==================

@bp.route('/por-empleado/<int:id_empleado>')
@login_required
def por_empleado(id_empleado):
    """Obtiene todos los documentos de un empleado específico"""
    documentos = db.session.execute(
        select(EmpleadosDocumento, TiposDocumentos)
        .join(TiposDocumentos, EmpleadosDocumento.id_tipo_documento == TiposDocumentos.id_tipo_documento)
        .where(EmpleadosDocumento.id_empleado == id_empleado)
        .order_by(TiposDocumentos.nombre)
    ).all()
    
    resultado = [
        {
            'id': doc.id_empleado_documento,
            'tipo': tipo.nombre,
            'valor': doc.valor_documento
        }
        for doc, tipo in documentos
    ]
    
    return jsonify(resultado)