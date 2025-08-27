import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = Email("b231160@skit.ac.in", "LIFE_CONNECT")

def send_email(subject, to_emails, body):
    if not isinstance(to_emails, list):
        to_emails = [to_emails]

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        for email in to_emails:
            message = Mail(
                from_email=FROM_EMAIL,
                to_emails=email,
                subject=subject,
                html_content=body
            )
            response = sg.send(message)
            print(f"📩 Email sent to {email}! Status: {response.status_code}")
    except Exception as e:
        print("❌ Error while sending email:", e)
