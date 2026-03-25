#!/bin/bash
echo "🚀 Actualizando la aplicación..."
# Entrar a la carpeta de la app y bajar cambios de Git
cd /vps/clientes/bolos
git pull

# Volver un nivel y reconstruir los contenedores
docker compose up -d --build

echo "✅ ¡Todo listo y corriendo!"
