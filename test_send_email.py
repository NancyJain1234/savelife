from send_email import send_email

if __name__ == "__main__":
    subject = "Test Email from SaveLife"
    to_emails = ["b231149@skit.ac.in"]   # send test to yourself
    body = """
    <h2>✅ Test Email</h2>
    <p>This is a test email from SaveLife using SendGrid.</p>
    """
    send_email(subject, to_emails, body)
