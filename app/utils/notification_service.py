from app import db
from models import Notificaciones, Clientes
from datetime import datetime
from sqlalchemy import func

def get_next_notification_id():
    """Get next available notification ID"""
    max_id = db.session.execute(
        func.max(Notificaciones.id_notificacion)
    ).scalar()
    return (max_id or 0) + 1

def crear_notificacion(id_cliente, titulo, mensaje, tipo='info'):
    """
    Create a notification for a client
    
    Args:
        id_cliente: Client ID
        titulo: Notification title
        mensaje: Notification message
        tipo: Type (info, success, warning, error, prestamo, venta, devolucion)
    """
    try:
        notificacion = Notificaciones(
            id_notificacion=get_next_notification_id(),
            id_cliente=id_cliente,
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            leido=False,
            fecha_envio=datetime.now()
        )
        
        db.session.add(notificacion)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error creating notification: {str(e)}")
        return False

def notificar_venta_completada(venta, cliente):
    """Notify customer about completed sale"""
    titulo = f"Compra Completada - Factura {venta.numero_factura}"
    mensaje = f"Tu compra por un total de L {venta.total:,.2f} ha sido procesada exitosamente. Factura: {venta.numero_factura}"
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='venta')

def notificar_venta_pendiente(venta, cliente):
    """Notify customer about pending payment"""
    titulo = f"Pago Pendiente - Factura {venta.numero_factura}"
    mensaje = f"Tu orden ha sido registrada. Total: L {venta.total:,.2f}. Esperando confirmación de pago."
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='warning')

def notificar_pago_confirmado(venta, cliente):
    """Notify customer about payment confirmation"""
    titulo = f"Pago Confirmado"
    mensaje = f"Tu pago de L {venta.total:,.2f} ha sido confirmado. Factura: {venta.numero_factura}"
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='success')

def notificar_prestamo_creado(prestamo, cliente, libro):
    """Notify customer about new loan"""
    titulo = f"Préstamo Aprobado"
    mensaje = f'Has recibido el préstamo del libro "{libro.titulo}". Fecha de devolución: {prestamo.fecha_devolucion_estimada.strftime("%d/%m/%Y")}'
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='prestamo')

def notificar_devolucion_proxima(prestamo, cliente, libro, dias_restantes):
    """Notify customer about upcoming return"""
    titulo = f"Recordatorio de Devolución"
    mensaje = f'El préstamo del libro "{libro.titulo}" vence en {dias_restantes} días. Fecha límite: {prestamo.fecha_devolucion_estimada.strftime("%d/%m/%Y")}'
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='warning')

def notificar_devolucion_vencida(prestamo, cliente, libro):
    """Notify customer about overdue return"""
    titulo = f"⚠️ Devolución Vencida"
    mensaje = f'El préstamo del libro "{libro.titulo}" está vencido. Por favor, devuélvelo lo antes posible para evitar multas adicionales.'
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='error')

def notificar_devolucion_completada(prestamo, cliente, libro):
    """Notify customer about completed return"""
    titulo = f"Devolución Completada"
    mensaje = f'La devolución del libro "{libro.titulo}" ha sido registrada exitosamente. ¡Gracias!'
    crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='success')

def notificar_nuevo_libro(libro, categorias=None):
    """Notify all active customers about new book (batch notification)"""
    titulo = f"📚 Nuevo Libro Disponible"
    mensaje = f'Nuevo libro agregado al catálogo: "{libro.titulo}". ¡Encuéntralo ahora en nuestra biblioteca!'
    
    try:
        # Get all active clients
        clientes = db.session.query(Clientes).filter_by(activo=1).all()
        
        for cliente in clientes:
            crear_notificacion(cliente.id_cliente, titulo, mensaje, tipo='info')
        
        return True
    except Exception as e:
        print(f"Error sending bulk notifications: {str(e)}")
        return False

def notificar_stock_bajo_admin(libro, stock_actual):
    """Notify administrators about low stock"""
    # This would notify admin users - you'd need to implement admin notification system
    pass