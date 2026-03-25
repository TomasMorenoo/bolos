#!/bin/bash

# ==========================================
# CONFIGURACIÓN (Cambia esto por tu ruta real)
# ==========================================
PROJECT_DIR="/vps/clientes/bolos"

# Moverse al directorio del proyecto automáticamente
cd "$PROJECT_DIR" || { echo "❌ Error: No se encontró el directorio $PROJECT_DIR"; exit 1; }

case "$1" in
    start|up|update)
        echo "🚀 Iniciando actualización de Bowling Tracker..."
        
        # 1. Bajar los últimos cambios de Git
        echo "📥 Obteniendo últimos cambios de Git..."
        git pull

        # 2. Asegurar que la base de datos exista para no romper los volúmenes
        if [ ! -f "bowling.db" ]; then
            echo "📁 Creando bowling.db para persistencia de datos..."
            touch bowling.db
        fi

        # 3. Reconstruir y levantar contenedores
        echo "🐳 Construyendo y levantando servicios..."
        docker compose up -d --build
        
        echo "✅ ¡Todo listo y corriendo en el puerto 5002!"
        ;;
    stop|down)
        echo "🛑 Deteniendo Bowling Tracker..."
        docker compose down
        echo "✅ Contenedor detenido."
        ;;
    restart)
        echo "🔄 Reiniciando Bowling Tracker..."
        docker compose restart
        echo "✅ Reinicio completado."
        ;;
    logs)
        echo "📄 Mostrando logs en vivo (Presiona Ctrl+C para salir)..."
        docker compose logs -f
        ;;
    *)
        echo "🎳 Comando no reconocido."
        echo "Uso: up-bolos {start|stop|restart|logs}"
        echo "Nota: 'start' automáticamente hace un git pull antes de levantar."
        exit 1
        ;;
esac