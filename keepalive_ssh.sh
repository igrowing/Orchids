#!/bin/bash
COUNTER=0
FILE=/dev/shm/keep_ssh

while true; do
  # sleep 1 minute
  sleep 60
  # check file, increment counter if file is missing
  if ! test -e $FILE ; then 
    let COUNTER+=1
  fi
  # remove file
  rm -f $FILE
  # If 3 minutes no file appears then restart all ssh and the counter
  if [  $COUNTER -gt 2 ]; then
    logger Exceeded timeout of non-responsive SSH for more than $COUNTER minutes. Killing all ssh.
    killall ssh
    # restartd will restart all reverse ssh sessions.
    let COUNTER=0
  fi
done
