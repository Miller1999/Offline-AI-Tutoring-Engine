## Objetivo
Validar empíricamente la viabilidad técnica del núcleo de la arquitectura propuesta en la tesis (Evaluación Aislada + RAG Local + IA Cuantizada en un solo turno), operando 100% offline y en hardware de recursos limitados.
### Resumen
Se construyó exitosamente un orquestador en Python (`orquestador.py`) que automatiza el ciclo completo de evaluación de un estudiante. El sistema es capaz de instanciar un contenedor Docker efímero y sin red para ejecutar código no confiable, extraer el error estructurado generado por Pytest, enriquecer el contexto mediante una base de datos vectorial local (ChromaDB) e interactuar con un Modelo de Lenguaje de 3B parámetros (Qwen 2.5 Coder) vía Ollama para generar retroalimentación socrática segura.
[[Flujo de operacion]] 
[[Componentes construidos]]
[[Hitos técnicos y validación de hipótesis]]
