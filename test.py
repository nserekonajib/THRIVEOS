import smtplib
from email.message import EmailMessage
import ssl


def test_send_email():
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    EMAIL_ADDRESS = "nserekonajib3@gmail.com"
    EMAIL_PASSWORD = "qrsf zfbl rjmv pcgf"  # App Password (no spaces when stored)

    TO_EMAIL = "zayyanclenza@gmail.com"

    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg["Subject"] = "Test Email – SMTP Verification"
    msg.set_content("This is a test email to verify SMTP configuration.")

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()

            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        print("✅ Test email sent successfully")

    except Exception as e:
        print("❌ Email sending failed:")
        print(e)


test_send_email()