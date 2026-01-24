from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func
from models import FacturasSar, Sucursales, Venta
from app import db
from datetime import datetime, date

bp = Blueprint('sar', __name__, url_prefix='/sar')

# ================== FUNCIONES AUXILIARES ==================

def get_next_parametro_id():
    """Obtiene el siguiente ID disponible para FacturasSar"""
    max_id = db.session.execute(
        select(func.max(FacturasSar.id_parametro))
    ).scalar()
    return (max_id or 0) + 1

def get_parametro_sar_activo(sucursal_id):
    """Obtiene el parámetro SAR activo para una sucursal"""
    parametro = db.session.execute(
        select(FacturasSar)
        .where(
            FacturasSar.id_sucursal == sucursal_id,
            FacturasSar.anulada == 0,
            FacturasSar.id_venta == None  # ← Only get parameter ranges, not individual invoices
        )
        .order_by(FacturasSar.id_parametro.desc())
    ).scalars().first()
    
    return parametro

# Add this function after get_parametro_sar_activo
def validar_sar_para_venta(sucursal_id):
    """
    Valida si el SAR está configurado correctamente para realizar una venta
    Retorna: (es_valido, mensaje_error, parametro_sar)
    """
    parametro = get_parametro_sar_activo(sucursal_id)
    
    if not parametro:
        return False, "No hay un parámetro SAR configurado para esta sucursal. Contacte al administrador.", None
    
    # Verificar si está anulado
    if parametro.anulada:
        return False, "El parámetro SAR de esta sucursal está anulado. Configure uno nuevo.", None
    
    # Verificar fecha de vencimiento
    if parametro.rango_inicial < date.today():
        return False, f"El rango SAR ha vencido (venció el {parametro.rango_inicial.strftime('%d/%m/%Y')}). Configure un nuevo rango.", None
    
    # Verificar si hay facturas disponibles
    if parametro.ultima_factura:
        correlativo_actual = int(parametro.ultima_factura.split('-')[-1])
        rango_final_num = int(parametro.rango_final.split('-')[-1])
        
        if correlativo_actual >= rango_final_num:
            return False, "El rango de facturación está agotado. Configure un nuevo rango SAR.", None
    
    return True, "", parametro

# Add EDIT route after crear()
@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Editar parámetro SAR"""
    parametro = db.session.get(FacturasSar, id)
    
    if not parametro:
        flash('Parámetro SAR no encontrado', 'error')
        return redirect(url_for('sar.listar'))
    
    # No permitir editar parámetros anulados
    if parametro.anulada:
        flash('No se puede editar un parámetro SAR anulado', 'error')
        return redirect(url_for('sar.ver', id=id))
    
    # No permitir editar si ya tiene facturas emitidas
    if parametro.ultima_factura:
        flash('⚠️ No se puede editar un parámetro SAR que ya tiene facturas emitidas', 'error')
        return redirect(url_for('sar.ver', id=id))
    
    if request.method == 'POST':
        try:
            id_sucursal = int(request.form.get('id_sucursal'))
            cai = request.form.get('cai').strip()
            rtn_empresa = request.form.get('rtn_empresa').strip()
            rango_inicial = datetime.strptime(request.form.get('rango_inicial'), '%Y-%m-%d').date()
            fecha_emision = datetime.strptime(request.form.get('fecha_emision'), '%Y-%m-%d').date()
            rango_final = request.form.get('rango_final').strip()
            
            # Validaciones
            if len(cai) < 20:
                flash('El CAI debe tener al menos 20 caracteres', 'error')
                return redirect(url_for('sar.editar', id=id))
            
            if len(rtn_empresa) != 14:
                flash('El RTN debe tener 14 dígitos', 'error')
                return redirect(url_for('sar.editar', id=id))
            
            # Validar formato de rango_final
            partes = rango_final.split('-')
            if len(partes) != 4:
                flash('Formato de rango final inválido. Debe ser: 000-001-01-00001000', 'error')
                return redirect(url_for('sar.editar', id=id))
            
            # Actualizar parámetro
            parametro.id_sucursal = id_sucursal
            parametro.cai = cai
            parametro.rtn_empresa = rtn_empresa
            parametro.rango_inicial = rango_inicial
            parametro.fecha_emision = fecha_emision
            parametro.rango_final = rango_final
            
            db.session.commit()
            
            flash('✅ Parámetro SAR actualizado exitosamente', 'success')
            return redirect(url_for('sar.ver', id=id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar parámetro SAR: {str(e)}', 'error')
            return redirect(url_for('sar.editar', id=id))
    
    # GET
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    return render_template('sar/editar.html', parametro=parametro, sucursales=sucursales)

def validar_rango_factura(parametro, numero_correlativo):
    """Valida si un número correlativo está dentro del rango autorizado"""
    # Extraer número del rango_final (formato: 000-001-01-00001000)
    try:
        rango_final_num = int(parametro.rango_final.split('-')[-1])
        return numero_correlativo <= rango_final_num
    except:
        return False

def generar_numero_factura_sar(parametro):
    """
    Genera el siguiente número de factura según SAR de Honduras
    Formato: 000-001-01-00000001
    Estructura: ESTABLECIMIENTO-PUNTO_EMISION-TIPO_DOCUMENTO-CORRELATIVO
    """
    if not parametro.ultima_factura:
        # Primera factura del rango
        base = parametro.rango_final.rsplit('-', 1)[0]  # 000-001-01
        return f"{base}-00000001"
    
    # Incrementar última factura
    partes = parametro.ultima_factura.split('-')
    correlativo = int(partes[-1]) + 1
    
    # Validar que no exceda el rango
    if not validar_rango_factura(parametro, correlativo):
        raise ValueError("Se ha alcanzado el límite del rango de facturación autorizado")
    
    # Reconstruir número
    base = '-'.join(partes[:-1])
    return f"{base}-{correlativo:08d}"

# ================== RUTAS CRUD ==================

@bp.route('/')
@login_required
def listar():
    
    # Get all SAR parameters with branch info and usage stats
    parametros_data = []
    parametros = db.session.execute(
        select(FacturasSar, Sucursales)
        .join(Sucursales, FacturasSar.id_sucursal == Sucursales.id_sucursal)
        .order_by(FacturasSar.rango_inicial.desc())
    ).all()
    
    for parametro, sucursal in parametros:
        # Calculate usage
        if parametro.ultima_factura:
            correlativo_actual = int(parametro.ultima_factura.split('-')[-1])
        else:
            correlativo_actual = 0
        
        rango_final_num = int(parametro.rango_final.split('-')[-1])
        facturas_disponibles = rango_final_num - correlativo_actual
        porcentaje_usado = (correlativo_actual / rango_final_num) * 100 if rango_final_num > 0 else 0
        
        # Determine status
        if parametro.anulada:
            status = 'anulado'
            status_class = 'danger'
        elif facturas_disponibles < 100:
            status = 'crítico'
            status_class = 'danger'
        elif porcentaje_usado > 80:
            status = 'advertencia'
            status_class = 'warning'
        else:
            status = 'activo'
            status_class = 'success'
        
        parametros_data.append({
            'parametro': parametro,
            'sucursal': sucursal,
            'correlativo_actual': correlativo_actual,
            'rango_final_num': rango_final_num,
            'facturas_disponibles': facturas_disponibles,
            'porcentaje_usado': porcentaje_usado,
            'status': status,
            'status_class': status_class
        })
    
    return render_template('sar/listar.html', parametros_data=parametros_data)

@bp.route('/crear', methods=['GET', 'POST'])
@login_required
def crear():
    """Crear nuevo parámetro SAR"""

    if request.method == 'POST':
        try:
            id_sucursal = int(request.form.get('id_sucursal'))
            cai = request.form.get('cai').strip()
            rtn_empresa = request.form.get('rtn_empresa').strip()
            rango_inicial = datetime.strptime(request.form.get('rango_inicial'), '%Y-%m-%d').date()
            fecha_emision = datetime.strptime(request.form.get('fecha_emision'), '%Y-%m-%d').date()
            rango_final = request.form.get('rango_final').strip()  # Formato: 000-001-01-00001000
            
            # Validaciones
            if len(cai) < 20:
                flash('El CAI debe tener al menos 20 caracteres', 'error')
                return redirect(url_for('sar.crear'))
            
            if len(rtn_empresa) != 14:
                flash('El RTN debe tener 14 dígitos', 'error')
                return redirect(url_for('sar.crear'))
            
            # Validar formato de rango_final
            partes = rango_final.split('-')
            if len(partes) != 4:
                flash('Formato de rango final inválido. Debe ser: 000-001-01-00001000', 'error')
                return redirect(url_for('sar.crear'))
            
            # Check if there's already an active SAR for this branch
            parametro_existente = get_parametro_sar_activo(id_sucursal)
            if parametro_existente:
                flash('⚠️ Advertencia: Ya existe un parámetro SAR activo para esta sucursal. Se recomienda anular el anterior antes de crear uno nuevo.', 'warning')
            
            nuevo_parametro = FacturasSar(
                id_parametro=get_next_parametro_id(),
                id_venta=None,
                id_sucursal=id_sucursal,
                cai=cai,
                rango_inicial=rango_inicial,
                fecha_emision=fecha_emision,
                rango_final=rango_final,
                rtn_empresa=rtn_empresa,
                anulada=0,
                fecha_anulacion=None,
                ultima_factura=None
            )
            
            db.session.add(nuevo_parametro)
            db.session.commit()
            
            flash('✅ Parámetro SAR creado exitosamente', 'success')
            return redirect(url_for('sar.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear parámetro SAR: {str(e)}', 'error')
            return redirect(url_for('sar.crear'))
    
    # GET
    sucursales = db.session.execute(
        select(Sucursales).where(Sucursales.activo == 1).order_by(Sucursales.nombre)
    ).scalars().all()
    
    return render_template('sar/crear.html', sucursales=sucursales)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """Ver detalles de un parámetro SAR"""
    resultado = db.session.execute(
        select(FacturasSar, Sucursales)
        .join(Sucursales, FacturasSar.id_sucursal == Sucursales.id_sucursal)
        .where(FacturasSar.id_parametro == id)
    ).first()
    
    if not resultado:
        flash('Parámetro SAR no encontrado', 'error')
        return redirect(url_for('sar.listar'))
    
    parametro, sucursal = resultado
    
    # Calcular facturas usadas
    if parametro.ultima_factura:
        correlativo_actual = int(parametro.ultima_factura.split('-')[-1])
    else:
        correlativo_actual = 0
    
    rango_final_num = int(parametro.rango_final.split('-')[-1])
    facturas_disponibles = rango_final_num - correlativo_actual
    porcentaje_usado = (correlativo_actual / rango_final_num) * 100 if rango_final_num > 0 else 0
    
    # Get sales using this SAR parameter
    ventas_count = db.session.execute(
        select(func.count(Venta.id_venta))
        .join(FacturasSar, Venta.id_venta == FacturasSar.id_venta)
        .where(FacturasSar.id_parametro == id)
    ).scalar() or 0
    
    return render_template('sar/ver.html',
                         parametro=parametro,
                         sucursal=sucursal,
                         correlativo_actual=correlativo_actual,
                         rango_final_num=rango_final_num,
                         facturas_disponibles=facturas_disponibles,
                         porcentaje_usado=porcentaje_usado,
                         ventas_count=ventas_count)

@bp.route('/verificar/<int:sucursal_id>')
@login_required
def verificar_sar(sucursal_id):
    """Check SAR configuration status for a branch - API endpoint"""
    parametro = get_parametro_sar_activo(sucursal_id)
    
    if not parametro:
        return jsonify({
            'status': 'none', 
            'message': 'No hay parámetros SAR configurados para esta sucursal'
        })
    
    # Check if nearing limit
    if parametro.ultima_factura:
        current = int(parametro.ultima_factura.split('-')[-1])
        limit = int(parametro.rango_final.split('-')[-1])
        remaining = limit - current
        percent_used = (current / limit) * 100
        
        if remaining == 0:
            return jsonify({
                'status': 'exhausted',
                'message': 'El rango de facturación está agotado. Configure un nuevo rango SAR.',
                'remaining': 0,
                'percent_used': 100
            })
        elif remaining < 100:
            return jsonify({
                'status': 'critical',
                'message': f'⚠️ CRÍTICO: Solo quedan {remaining} facturas disponibles',
                'remaining': remaining,
                'percent_used': percent_used
            })
        elif percent_used > 80:
            return jsonify({
                'status': 'warning',
                'message': f'Advertencia: {percent_used:.1f}% del rango SAR utilizado',
                'remaining': remaining,
                'percent_used': percent_used
            })
    
    return jsonify({
        'status': 'ok', 
        'message': 'SAR configurado correctamente'
    })

@bp.route('/anular/<int:id>', methods=['POST'])
@login_required
def anular(id):
    """Anular un parámetro SAR"""
    
    try:
        parametro = db.session.get(FacturasSar, id)
        
        if not parametro:
            flash('Parámetro SAR no encontrado', 'error')
            return redirect(url_for('sar.listar'))
        
        if parametro.anulada:
            flash('Este parámetro SAR ya está anulado', 'warning')
            return redirect(url_for('sar.ver', id=id))
        
        parametro.anulada = 1
        parametro.fecha_anulacion = datetime.now()
        
        db.session.commit()
        
        flash('✅ Parámetro SAR anulado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al anular parámetro SAR: {str(e)}', 'error')
    
    return redirect(url_for('sar.ver', id=id))