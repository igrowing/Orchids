#!/usr/bin/env python
'''
Module for (relatively) safe and easy send Pushbullet Note from Python environments (like Django).
Secure details must be provided in separated file private.py as shown in private.py.sample.

The module is easy publish-able.      *** Do not publish your private.py file. ***

Usage as module:
    import pushb  # private.py must be ready.
    pushb.send_note('Test-icles', 'Perfect body')

Usage as standalone:
    python pushb.py 'Test-icles' 'Perfect body'

Requirements:
    See Source: https://github.com/Azelphur/pyPushBullet

Author: iGrowing

'''

import sys
import private
from pushbullet import PushBullet

def send_note(title, body):
    '''Sends Pushbullet notification to all mobile devices linked to your account.
    The account details are derived from PUSHBULLET_API_KEY provided in private.py.
    Title and body text must be provided.
    '''
    if type(private.PUSHBULLET_API_KEY) != iter:
        private.PUSHBULLET_API_KEY = [private.PUSHBULLET_API_KEY]

    for key in private.PUSHBULLET_API_KEY:
        p = PushBullet(key)
        devices = p.getDevices()
        for d in devices:
            if d['icon'] == 'phone':
                p.pushNote(d['iden'], title=title, body=body)


# Use this trick to execute the file. Normally, it's a module to be imported.
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print "Usage as standalone:\n    python pushb.py 'Test-icles' 'Perfect body'"
        sys.exit(1)

    send_note(sys.argv[1], sys.argv[2])
