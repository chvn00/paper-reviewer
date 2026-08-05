#!/bin/zsh
cd "${0:A:h}" || exit 1
clear
python3 app.py conversar
status=$?
echo
if [[ $status -ne 0 ]]; then
  echo "La aplicación terminó con un error. Revisa el mensaje anterior."
fi
echo "Puedes cerrar esta ventana."
read -k 1
