from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select
from models import MetodoDePago
from app import db
from datetime import datetime

bp = Blueprint('metodos_pago', __name__, url_prefix='/metodos-pago')

# ================== HELPER FUNCTIONS ==================

def get_next_metodo_id():
    """Get the next available ID for MetodoDePago"""
    from sqlalchemy import func
    max_id = db.session.execute(
        select(func.max(MetodoDePago.id_metodo_pago))
    ).scalar()
    return (max_id or 0) + 1


# ================== CRUD ROUTES ==================

@bp.route('/')
@login_required
def listar():
    
    # Get all payment methods
    metodos = db.session.execute(
        select(MetodoDePago).order_by(MetodoDePago.nombre)
    ).scalars().all()
    
    return render_template('metodos_pago/listar.html', metodos=metodos)

@bp.route('/crear', methods=['GET', 'POST'])
@login_required
def crear():
    """Create a new payment method"""

    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            activo = 1 if request.form.get('activo') else 0
            
            # Validation
            if not nombre:
                flash('El nombre es requerido', 'error')
                return redirect(url_for('metodos_pago.crear'))
            
            if not descripcion:
                flash('La descripción es requerida', 'error')
                return redirect(url_for('metodos_pago.crear'))
            
            # Check if name already exists
            existente = db.session.execute(
                select(MetodoDePago).where(MetodoDePago.nombre == nombre)
            ).scalars().first()
            
            if existente:
                flash('Ya existe un método de pago con ese nombre', 'warning')
                return redirect(url_for('metodos_pago.crear'))
            
            # Create new payment method
            nuevo_metodo = MetodoDePago(
                id_metodo_pago=get_next_metodo_id(),
                nombre=nombre,
                descripcion=descripcion,
                activo=activo
            )
            
            db.session.add(nuevo_metodo)
            db.session.commit()
            
            flash(f'✅ Método de pago "{nombre}" creado exitosamente', 'success')
            return redirect(url_for('metodos_pago.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear método de pago: {str(e)}', 'error')
            return redirect(url_for('metodos_pago.crear'))
    
    return render_template('metodos_pago/crear.html')

@bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar(id):
    """Edit a payment method"""
    
    metodo = db.session.get(MetodoDePago, id)
    
    if not metodo:
        flash('Método de pago no encontrado', 'error')
        return redirect(url_for('metodos_pago.listar'))
    
    if request.method == 'POST':
        try:
            nombre = request.form.get('nombre', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            activo = 1 if request.form.get('activo') else 0
            
            # Validation
            if not nombre:
                flash('El nombre es requerido', 'error')
                return redirect(url_for('metodos_pago.editar', id=id))
            
            if not descripcion:
                flash('La descripción es requerida', 'error')
                return redirect(url_for('metodos_pago.editar', id=id))
            
            # Check if name already exists (exclude current)
            existente = db.session.execute(
                select(MetodoDePago).where(
                    MetodoDePago.nombre == nombre,
                    MetodoDePago.id_metodo_pago != id
                )
            ).scalars().first()
            
            if existente:
                flash('Ya existe otro método de pago con ese nombre', 'warning')
                return redirect(url_for('metodos_pago.editar', id=id))
            
            # Update payment method
            metodo.nombre = nombre
            metodo.descripcion = descripcion
            metodo.activo = activo
            
            db.session.commit()
            
            flash(f'✅ Método de pago "{nombre}" actualizado exitosamente', 'success')
            return redirect(url_for('metodos_pago.listar'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar método de pago: {str(e)}', 'error')
            return redirect(url_for('metodos_pago.editar', id=id))
    
    return render_template('metodos_pago/editar.html', metodo=metodo)

@bp.route('/ver/<int:id>')
@login_required
def ver(id):
    """View payment method details"""
    
    metodo = db.session.get(MetodoDePago, id)
    
    if not metodo:
        flash('Método de pago no encontrado', 'error')
        return redirect(url_for('metodos_pago.listar'))
    
    # Get usage statistics
    from models import Venta
    from sqlalchemy import func
    
    ventas_count = db.session.execute(
        select(func.count(Venta.id_venta)).where(
            Venta.id_metodo_pago == id
        )
    ).scalar() or 0
    
    return render_template('metodos_pago/ver.html', 
                         metodo=metodo, 
                         ventas_count=ventas_count)

@bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar(id):
    """Delete a payment method (only if not in use)"""
    
    try:
        metodo = db.session.get(MetodoDePago, id)
        
        if not metodo:
            flash('Método de pago no encontrado', 'error')
            return redirect(url_for('metodos_pago.listar'))
        
        # Check if method is in use
        from models import Venta
        from sqlalchemy import func
        
        ventas_count = db.session.execute(
            select(func.count(Venta.id_venta)).where(
                Venta.id_metodo_pago == id
            )
        ).scalar() or 0
        
        if ventas_count > 0:
            flash(f'No se puede eliminar este método de pago porque está asociado a {ventas_count} venta(s)', 'warning')
            return redirect(url_for('metodos_pago.ver', id=id))
        
        nombre = metodo.nombre
        db.session.delete(metodo)
        db.session.commit()
        
        flash(f'✅ Método de pago "{nombre}" eliminado exitosamente', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar método de pago: {str(e)}', 'error')
    
    return redirect(url_for('metodos_pago.listar'))

@bp.route('/toggle-activo/<int:id>', methods=['POST'])
@login_required
def toggle_activo(id):
    """Toggle active status of a payment method"""
    
    try:
        metodo = db.session.get(MetodoDePago, id)
        
        if not metodo:
            return jsonify({'success': False, 'error': 'No encontrado'}), 404
        
        metodo.activo = 1 - metodo.activo
        db.session.commit()
        
        estado = 'activado' if metodo.activo else 'desactivado'
        return jsonify({
            'success': True, 
            'message': f'Método {estado}',
            'activo': metodo.activo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500