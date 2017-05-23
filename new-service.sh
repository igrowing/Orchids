#!/bin/bash
# On courtesy of naholyr: https://gist.github.com/naholyr/4275302
# Slightly modified.

SERVICE_FILE=$(tempfile)

echo "--- Download template ---"
wget -q -O "$SERVICE_FILE" 'https://gist.githubusercontent.com/naholyr/4275302/raw/9df4ef3f4f2c294c9585f11d1c8593b62bdd52d3/service.sh'
chmod +x "$SERVICE_FILE"
echo ""

echo "--- Customize ---"
echo "I'll now ask you some information to customize script"
echo "Press Ctrl+C anytime to abort."
echo "Empty values are not accepted."
echo ""

prompt_token() {
  local VAL=""
  while [ "$VAL" = "" ]; do
    echo -n "${2:-$1} : "
    read VAL
    if [ "$VAL" = "" ]; then
      echo "Please provide a value"
    fi
  done
  VAL=$(printf '%q' "$VAL")
  eval $1=$VAL
  sed -i "s/<$1>/$(printf '%q' "$VAL")/g" $SERVICE_FILE
}

prompt_token 'NAME'        'Service name'
if [ -f "/etc/init.d/$NAME" ]; then
  echo "Error: service '$NAME' already exists"
  exit 1
fi

prompt_token 'DESCRIPTION' ' Description'
prompt_token 'COMMAND'      '     Command'
prompt_token 'USERNAME'    '        User'
if ! id -u "$USERNAME" &> /dev/null; then
  echo "Error: user '$USERNAME' not found"
  exit 1
fi

echo ""

echo "--- Installation ---"
if [ ! -w /etc/init.d ]; then
  echo "You don't gave me enough permissions to install service myself."
  echo "That's smart, always be really cautious with third-party shell scripts!"
  echo "Check content of temporary script in /tmp: it may not contain your run command."
  echo "If so, edit the temporary script and add your command manually. This happens if command contain slashes."
  echo "You should now type those commands as superuser to install and run your service:"
  echo ""
  echo "   sudo mv \"$SERVICE_FILE\" \"/etc/init.d/$NAME\""
  echo "   sudo touch \"/var/log/$NAME.log\" && sudo chown \"$USERNAME\" \"/var/log/$NAME.log\""
  echo "   sudo update-rc.d $NAME defaults"
  echo "   sudo service $NAME start"
else
  echo "1. mv \"$SERVICE_FILE\" \"/etc/init.d/$NAME\""
  mv -v "$SERVICE_FILE" "/etc/init.d/$NAME"
  echo "2. touch \"/var/log/$NAME.log\" && chown \"$USERNAME\" \"/var/log/$NAME.log\""
  touch "/var/log/$NAME.log" && chown "$USERNAME" "/var/log/$NAME.log"
  echo "3. update-rc.d \"$NAME\" defaults"
  update-rc.d "$NAME" defaults
  echo "4. service \"$NAME\" start"
  service "$NAME" start
fi

echo ""
echo "---Uninstall instructions ---"
echo "The service can uninstall itself:"
echo "    service \"$NAME\" uninstall"
echo "It will simply run update-rc.d -f \"$NAME\" remove && rm -f \"/etc/init.d/$NAME\""
echo ""
echo "--- Terminated ---"
