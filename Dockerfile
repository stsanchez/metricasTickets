# 1. Usar una imagen oficial de Python con tu versión específica
FROM python:3.13.3-slim

# 2. Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# 3. Copiar el archivo de requerimientos
COPY requirements.txt .

# 4. Instalar las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copiar el resto del código de la aplicación
COPY . .

# 6. Exponer el puerto en el que correrá Gunicorn
EXPOSE 5000

# 7. Comando para correr la aplicación cuando se inicie el contenedor
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "app:app"]