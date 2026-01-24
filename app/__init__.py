from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from app.utils.email_service import mail

# Inicializar SQLAlchemy
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    # Crear la aplicación Flask
    app = Flask(__name__, 
                static_folder='static',
                static_url_path='/static')
    
    # Cargar configuración
    app.config.from_object(Config)
    
    # Inicializar la base de datos con la app
    db.init_app(app)
    
    # Inicializar Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor inicia sesión para acceder a esta página.'
    mail.init_app(app)
    
    # Registrar blueprints (rutas)
    from app.routes import main
    from app.routes.auth import auth
    from app.routes.clientes import clientes_bp
    from app.routes.autores import autores_bp
    from app.routes.tipos_documentos import tipos_documentos_bp
    from app.routes.categorias import categorias_bp
    from app.routes.estado_usuarios import estado_usuarios_bp
    from app.routes.pais import pais_bp
    from app.routes.editoriales import editoriales_bp
    from app.routes.sucursales import sucursales_bp
    from app.routes import clientes_documento
    from app.routes import temas_foros, mensajes_foros
    from app.routes.empleados import bp as empleados_bp
    from app.routes import empleados_documento
    from app.routes.libros import bp as libros_bp
    from app.routes.prestamos import bp as prestamos_bp
    from app.routes.resenas import bp as resenas_bp
    from app.routes.tickets import tickets
    from app.routes.respuesta_tickets import respuesta_tickets
    from app.routes.inventarios import bp as inventarios_bp
    from app.routes.biblioteca_personal import bp as biblioteca_personal_bp
    from app.routes.devoluciones import bp as devoluciones_bp
    from app.routes.venta import bp as ventas_bp
    from app.routes.metodos_pago import bp as metodos_pago_bp
    from app.routes import sar
    from app.routes.notificaciones import bp as notificaciones_bp
    from app.routes.orden_compra import bp as orden_compra_bp
    from app.routes.precio_compra import bp as precio_compra_bp

    app.register_blueprint(precio_compra_bp)
    app.register_blueprint(orden_compra_bp)
    app.register_blueprint(mensajes_foros.bp)
    app.register_blueprint(temas_foros.bp)
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(autores_bp)
    app.register_blueprint(tipos_documentos_bp)
    app.register_blueprint(categorias_bp)
    app.register_blueprint(estado_usuarios_bp)
    app.register_blueprint(pais_bp)
    app.register_blueprint(editoriales_bp)
    app.register_blueprint(sucursales_bp)
    app.register_blueprint(clientes_documento.bp)
    app.register_blueprint(empleados_bp)
    app.register_blueprint(empleados_documento.bp)
    app.register_blueprint(libros_bp)
    app.register_blueprint(prestamos_bp)
    app.register_blueprint(resenas_bp)
    app.register_blueprint(tickets)
    app.register_blueprint(respuesta_tickets)
    app.register_blueprint(inventarios_bp)
    app.register_blueprint(biblioteca_personal_bp)
    app.register_blueprint(devoluciones_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(metodos_pago_bp)
    app.register_blueprint(sar.bp)
    app.register_blueprint(notificaciones_bp)

    return app

# REPLACE THIS FUNCTION:
@login_manager.user_loader
def load_user(user_id):
    """
    Load user from session - handles both Clientes and Empleados
    User ID format:
    - Clientes: just the numeric ID (e.g., "1", "2")
    - Empleados: prefixed with 'emp_' (e.g., "emp_1", "emp_2")
    """
    from models import Clientes, Empleados
    
    if user_id.startswith('emp_'):
        # It's an Empleado
        try:
            emp_id = int(user_id.replace('emp_', ''))
            return db.session.get(Empleados, emp_id)
        except (ValueError, TypeError):
            return None
    else:
        # It's a Cliente
        try:
            return db.session.get(Clientes, int(user_id))
        except (ValueError, TypeError):
            return None
        