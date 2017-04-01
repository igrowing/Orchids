#!/bin/bash
COUNTER=0  # for SSH tunnel
COUNT_W=0  # for HTTP tunnel
FILE=/dev/shm/keep_ssh

while true; do
  # sleep 1 minute
  sleep 60
  # check HTTP reverse tunnel is alive
  resp=`runuser -l pi -c 'ssh root@198.57.47.238 "timeout 30 curl localhost:10080 | tail -30"'`
  if ! [[ "$resp" =~ "Last" ]]; then
    let COUNT_W+=1
  fi
  if [ $COUNT_W -gt 2 ]; then
    PID=`ps -ef | grep ssh | grep 10080 | awk '{ print $2 }'`
    logger Exceeded timeout of non-responsive HTTP for more than $COUNT_W minutes. Killing old pid: $PID. Restarting HTTP reverse tunnel.
    kill -9 $PID
    sleep 5
    nohup ssh -fN -R 198.57.47.238:10080:localhost:8001 orchid@198.57.47.238 &
    let COUNT_W=0
  fi
  # check file, increment counter if file is missing
  if ! test -e $FILE ; then
    let COUNTER+=1
  fi
  # remove file
  rm -f $FILE
  # If 3 minutes no file appears then restart all ssh and the counter
  if [  $COUNTER -gt 2 ]; then
    PID=`ps -ef | grep ssh | grep 10022 | awk '{ print $2 }'`
    logger Exceeded timeout of non-responsive SSH for more than $COUNTER minutes. Killing old pid: $PID. Restarting SSH reverse tunnel.
    # restartd will restart all reverse ssh sessions.
    #service restartd restart
    kill -9 $PID
    sleep 5
    nohup ssh -fN -R 198.57.47.238:10022:localhost:22 orchid@198.57.47.238 &
    let COUNTER=0
  fi
done
