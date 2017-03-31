#!/bin/bash
# This is workaround for non-properly starting ssh reverse tunnels on system boot.
# The tunnel is not recognised as broken if loads before all network interfaces are up.
#
# Add call to this script from /etc/rc.local as:
# nohup /<full_path>/init.sh &
#
sleep 30
killall ssh
service restartd restart
