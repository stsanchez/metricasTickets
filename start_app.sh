#!/bin/bash

# Define la ruta absoluta a tu proyecto
PROJECT_DIR="/home/monitoreo/Escritorio/Stefano/metricasTickets"

# Define la ruta absoluta a tu entorno virtual
# Confirmado: tu entorno virtual se llama 'myproject_venv'
VENV_DIR="$PROJECT_DIR/myproject_venv"

# Navega al directorio de tu proyecto para que Gunicorn encuentre tu código
cd $PROJECT_DIR

# Activa el entorno virtual. Esto es CRUCIAL para que Gunicorn y Flask usen las librerías correctas.
source $VENV_DIR/bin/activate

# Comando para iniciar Gunicorn
# - --workers 4: Inicia 4 procesos Gunicorn. Puedes ajustar este número según los CPUs de tu servidor.
# - --bind 0.0.0.0:5000: Gunicorn escuchará en todas las interfaces de red en el puerto 5000.
# - app:app: Esto asume que tu aplicación Flask está en 'app.py' y la instancia de Flask se llama 'app'.
#            Si el nombre de tu archivo principal o tu instancia de app son diferentes, ajústalos aquí.
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
