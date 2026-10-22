# Usamos una imagen muy ligera de Python
FROM python:3.14-alpine

# Establecemos el directorio de trabajo
WORKDIR /app

# Instalamos pytest y el plugin para generar reportes JSON
RUN pip install --no-cache-dir pytest pytest-json-report

# El comando por defecto al iniciar el contenedor:
# Ejecuta pytest, genera el reporte JSON en la terminal (stdout) y no crea archivos residuales.
# Generamos el reporte en un archivo físico dentro del contenedor
CMD ["pytest", "test_ejercicio.py", "--json-report", "--json-report-file=reporte.json"]