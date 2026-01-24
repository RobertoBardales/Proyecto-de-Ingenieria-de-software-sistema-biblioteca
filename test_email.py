from app import create_app
from app.utils.email_service import send_email

app = create_app()

with app.app_context():
    try:
        send_email(
            subject="Test Email",
            recipients=["your-email@example.com"],  # Change to your email
            text_body="This is a test email from your Flask app!",
            html_body="<h1>Test Email</h1><p>This is a test email from your Flask app!</p>"
        )
        print("✅ Email sent successfully! Check your inbox.")
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")