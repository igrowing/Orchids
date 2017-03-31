#!/bin/bash
# This is server side of paired script for SSH reverse tunnel recovery.
# This adds a file in tmpfs of Raspberry Pi. This is kind of watchdog.
# Raspberry Pi part of the the pair removes the file and waits for new one.
# If no new file appears then Raspberry Pi knows the revers SSH is dead and restarts it.
#
# Add this file into crontab -e as:
# @reboot /root/bin/touch_rpi.sh
#
while true; do
  sleep 60
  /usr/bin/timeout 61 ssh -p 10022 pi@localhost touch /dev/shm/keep_ssh || true
done
