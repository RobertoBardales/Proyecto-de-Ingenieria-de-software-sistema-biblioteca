from flask import render_template, current_app
from flask_mail import Mail, Message
from threading import Thread
from datetime import datetime
import os

mail = Mail()

def send_async_email(app, msg):
    """Send email asynchronously"""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error sending email: {str(e)}")

def send_email(subject, recipients, text_body=None, html_body=None, attachments=None):
    """
    Send email with optional attachments
    
    Args:
        subject: Email subject
        recipients: List of recipient emails
        text_body: Plain text body
        html_body: HTML body
        attachments: List of tuples (filename, content_type, data)
    """
    msg = Message(
        subject=subject,
        recipients=recipients if isinstance(recipients, list) else [recipients],
        sender=current_app.config['MAIL_DEFAULT_SENDER']
    )
    
    if text_body:
        msg.body = text_body
    if html_body:
        msg.html = html_body
    
    # Add attachments if provided
    if attachments:
        for filename, content_type, data in attachments:
            msg.attach(filename, content_type, data)
    
    # Send asynchronously
    app = current_app._get_current_object()
    Thread(target=send_async_email, args=(app, msg)).start()

def send_invoice_email(venta, cliente, detalles, factura_sar=None, sucursal=None):
    """Send invoice via email to customer"""
    try:
        subject = f"Factura {venta.numero_factura} - {current_app.config['APP_NAME']}"
        
        # Render HTML email template
        html_body = render_template(
            'emails/invoice.html',
            venta=venta,
            cliente=cliente,
            detalles=detalles,
            factura_sar=factura_sar,
            sucursal=sucursal
        )
        
        # Plain text fallback
        text_body = f"""
Estimado/a {cliente.nombres} {cliente.apellidos},

Adjunto encontrará su factura {venta.numero_factura}.

Detalles de la compra:
- Fecha: {venta.fecha_venta.strftime('%d/%m/%Y %H:%M')}
- Total: L {venta.total:,.2f}

Gracias por su compra.

Atentamente,
{current_app.config['APP_NAME']}
        """
        
        send_email(
            subject=subject,
            recipients=[cliente.email],
            text_body=text_body,
            html_body=html_body
        )
        
        return True
    except Exception as e:
        print(f"Error sending invoice email: {str(e)}")
        return False

def send_payment_confirmation_email(venta, cliente):
    """Send payment confirmation email"""
    try:
        subject = f"Pago Confirmado - Factura {venta.numero_factura}"
        
        html_body = render_template(
            'emails/payment_confirmed.html',
            venta=venta,
            cliente=cliente
        )
        
        text_body = f"""
Estimado/a {cliente.nombres} {cliente.apellidos},

Su pago ha sido confirmado exitosamente.

Factura: {venta.numero_factura}
Monto: L {venta.total:,.2f}

Gracias por su compra.

Atentamente,
{current_app.config['APP_NAME']}
        """
        
        send_email(
            subject=subject,
            recipients=[cliente.email],
            text_body=text_body,
            html_body=html_body
        )
        
        return True
    except Exception as e:
        print(f"Error sending payment confirmation: {str(e)}")
        return False

def send_loan_reminder_email(prestamo, cliente, libro):
    """Send loan return reminder email"""
    try:
        subject = f"Recordatorio: Devolución de Préstamo"
        
        html_body = render_template(
            'emails/loan_reminder.html',
            prestamo=prestamo,
            cliente=cliente,
            libro=libro
        )
        
        text_body = f"""
Estimado/a {cliente.nombres} {cliente.apellidos},

Este es un recordatorio de que su préstamo del libro "{libro.titulo}" vence el {prestamo.fecha_devolucion_estimada.strftime('%d/%m/%Y')}.

Por favor, devuélvalo a tiempo para evitar multas.

Atentamente,
{current_app.config['APP_NAME']}
        """
        
        send_email(
            subject=subject,
            recipients=[cliente.email],
            text_body=text_body,
            html_body=html_body
        )
        
        return True
    except Exception as e:
        print(f"Error sending loan reminder: {str(e)}")
        return False