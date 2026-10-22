import chromadb
import os

def cargar_apuntes_a_chroma():
    print("Iniciando motor de ChromaDB local...")
    
    # 1. Creamos un cliente persistente. 
    # Esto creará una carpeta llamada "bd_vectorial" en tu disco duro.
    cliente = chromadb.PersistentClient(path="./bd_vectorial")
    
    # 2. Creamos (o cargamos si ya existe) una colección (como una tabla en SQL)
    coleccion = cliente.get_or_create_collection(name="material_clase")
    
    # 3. Leemos el archivo físico
    archivo_apuntes = "apuntes.md"
    if not os.path.exists(archivo_apuntes):
        print(f"Error: No se encontró el archivo {archivo_apuntes}")
        return
        
    with open(archivo_apuntes, "r", encoding="utf-8") as f:
        contenido = f.read()
        
    # 4. Insertamos el documento en la base de datos
    # ChromaDB se encarga de crear el embedding (vector matemático) automáticamente
    coleccion.add(
        documents=[contenido],
        metadatas=[{"tema": "diccionarios_python", "autor": "profesor"}],
        ids=["apunte_diccionarios_01"] # Un ID único para este fragmento
    )
    
    print("\n¡Éxito! Los apuntes han sido vectorizados y guardados en la carpeta ./bd_vectorial")

if __name__ == "__main__":
    cargar_apuntes_a_chroma()