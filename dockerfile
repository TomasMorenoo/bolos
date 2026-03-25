# Usamos una imagen oficial de Python ligera
FROM python:3.11-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos los requerimientos e instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto de los archivos del proyecto (app, templates, etc.)
COPY . .

# Exponemos el puerto 5002
EXPOSE 5002

# Ejecutamos la app con gunicorn en el puerto 5002 (4 workers para mejor rendimiento)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5002", "bowling_app:app"]