# Tema: Diccionarios en Python

Un diccionario es una estructura de datos que guarda pares de clave-valor.
Para iterar o extraer información de un diccionario, Python ofrece métodos específicos:

- Si quieres obtener solo las llaves (los nombres de las propiedades), debes usar el método `.keys()`.
- Si quieres obtener solo los valores almacenados dentro de esas llaves, debes usar el método `.values()`.
- Si necesitas ambos al mismo tiempo, utiliza `.items()`.

Es un error común confundir `.keys()` con `.values()` cuando se intenta procesar el contenido de un diccionario.