from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.config import settings
from typing import List


conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username or "",
    MAIL_PASSWORD=settings.mail_password or "",
    MAIL_FROM=settings.mail_from or settings.mail_username or "",
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_STARTTLS=settings.mail_starttls,
    MAIL_SSL_TLS=settings.mail_ssl_tls,
    USE_CREDENTIALS=settings.mail_use_credentials,
    VALIDATE_CERTS=settings.mail_validate_certs,
)


async def send_email(subject: str, body: str, recipients: List[str]) -> None:
    """Send an email using the configured SMTP server."""
    if not settings.mail_username or not settings.mail_password:
        print("Email not configured - skipping email send")
        return
    
    message = MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype="html",
    )
    
    fm = FastMail(conf)
    await fm.send_message(message)
    print(f"Email sent successfully to {', '.join(recipients)}")


async def send_alert_email(printer_name: str, alert_type: str, alert_message: str) -> None:
    """Send an alert email about a printer issue."""
    if not settings.alert_email_recipients:
        return
    
    recipients = [email.strip() for email in settings.alert_email_recipients.split(",")]
    
    subject = f"[Print Collect] Alerta: {alert_type} - {printer_name}"
    
    body = f"""
    <html>
        <body>
            <h2>Alerta do Sistema Print Collect</h2>
            <p><strong>Impressora:</strong> {printer_name}</p>
            <p><strong>Tipo de alerta:</strong> {alert_type}</p>
            <p><strong>Mensagem:</strong> {alert_message}</p>
            <br>
            <p>Acesse o painel para mais detalhes: {settings.cors_origins.split(',')[0]}</p>
        </body>
    </html>
    """
    
    await send_email(subject, body, recipients)
