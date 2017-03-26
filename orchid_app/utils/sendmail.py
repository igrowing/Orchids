#!/usr/bin/env python
'''
Module for (relatively) safe and easy mail send from Python environments (like Django).
Secure details must be provided in separated file private.py as shown in private.py.sample.
Your "sender" email account must allow "less secure apps" for module work.
Instructions for Gmail account of the "sender":
1. Log in to your account.
2. Go Settings -> Accounts and Import -> Other Google account settings.
3. Click "Connected apps & sites"
4. Tick the switch.
5. Close the Other Google account settings and logout of your sender account (optionally).

The module is easy publish-able.      *** Do not publish your private.py file. ***

Usage as module:
    import sendmail  # private.py must be ready.
    sendmail.sendmail('Test-icles', 'Perfect body')

Usage as standalone:
    python sendmail.py 'Test-icles' 'Perfect body'

Author: iGrowing

'''

import sys
import smtplib
import private
from email.MIMEText import MIMEText
from email.MIMEMultipart import MIMEMultipart

def sendmail(subject, body):
    '''Sends mail from your account to list of recipients provided in private.py.
    Subject and body text must be provided.
    '''

    msg = MIMEMultipart()
    msg['From'] = private.EMAIL_HOST_USER
    # Create recipient list as string for the MIME object. Pass actual contacts as list in sendmail().
    msg['To'] = '; '.join(private.CONTACTS)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP(private.EMAIL_HOST, private.EMAIL_PORT)
    if private.EMAIL_USE_TLS:
        server.starttls()
    server.login(msg['From'], private.EMAIL_HOST_PASSWORD)
    # Raise mail sending error.
    server.sendmail(msg['From'], private.CONTACTS, msg.as_string())
    server.quit()


# Use this trick to execute the file. Normally, it's a module to be imported.
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print "Usage as standalone:\n    python sendmail.py 'Test-icles' 'Perfect body'"
        sys.exit(1)

    sendmail(sys.argv[1], sys.argv[2])
