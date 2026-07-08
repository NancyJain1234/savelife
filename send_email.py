# send_email.py
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email

# Must be a verified sender in SendGrid
FROM_EMAIL = Email("b231160@skit.ac.in", "LIFE_CONNECT")  

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
if not SENDGRID_API_KEY:
    print("❌ WARNING: SENDGRID_API_KEY is not set. Emails will not be sent.")
else:
    print("✅ SendGrid API key loaded.")

def send_email(subject, to_emails, body):
    """
    Send an HTML email via SendGrid.
    :param subject: Email subject
    :param to_emails: single email or list of emails
    :param body: HTML content
    :return: True if sent, False otherwise
    """
    if not isinstance(to_emails, list):
        to_emails = [to_emails]

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        for email in to_emails:
            print(f"📩 Sending email to: {email}")
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=email,
                subject=subject,
                html_content=body
            )
            response = sg.send(message)
            print(f"Status: {response.status_code}, Body: {response.body}, Headers: {response.headers}")
        return True
    except Exception as e:
        print("❌ Error sending email:", e)
        return False
