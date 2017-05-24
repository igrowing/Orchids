#!/bin/bash    
prefix='cd /home/pi/Orchids/'

function exec {
    logger Firmware update running: "$*"
    $prefix && $*
    rc=`echo $?`
    if [ $rc -ne 0 ]; then
        logger Firmware update aborted at command: "$cmd" with returncode: $rc
        exit $rc
    fi
}

logger Firmware update start.
exec 'rm -f master.zip*'
exec 'wget https://github.com/igrowing/orchids/archive/master.zip'
exec 'unzip -quo master.zip'
exec 'rsync -a Orchids-master/* ./'
exec 'rm -rf Orchids-master master.zip*'
logger Firmware update completed.

