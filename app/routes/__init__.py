from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from datetime import datetime

# Crear el blueprint principal
main = Blueprint('main', __name__)

@main.route('/')
def index():
    """Main route - shows landing or storefront based on login status"""
    if current_user.is_authenticated:
        # Usuario logueado -> mostrar storefront
        current_date = datetime.now().strftime('%d de %B del %Y')
        current_time = datetime.now().strftime('%H:%M')
        return render_template('storefront.html',
                              current_date=current_date,
                             current_time=current_time)
    else:
        # Usuario NO logueado -> mostrar landing page
        return render_template('landing.html')

@main.route('/dashboard')
def dashboard():
    """Dashboard - accessible to all authenticated users"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    
    current_date = datetime.now().strftime('%d de %B del %Y')
    current_time = datetime.now().strftime('%H:%M')
    return render_template('dashboard.html',
                          current_date=current_date,
                          current_time=current_time)

@main.route('/libros')
def libros():
    return "Aquí irán los libros"

@main.route('/clientes')
def usuarios():
    return "Aquí irán los usuarios"