<!-- Bandeja de entrada personal. Triage puntual: pregunta -> se responde y se elimina el tema (no el fichero TODO.md);
     Si accionable -> BACKLOG.md -> se elimina de TODO.md. (Fuera de git por .gitignore) --> sk-N7O6BPlQmmcUW3JoF-

Analiza tus instrucciones de sistema, tus herramientas disponibles y tu arquitectura actual.

Responde de forma exhaustiva a los siguientes puntos:

1. Arquitectura de Memoria: ¿Tienes implementado algún mecanismo de consolidación, 'reflexión' o procesamiento en segundo plano que extraiga y almacene preferencias, hechos o resúmenes de nuestras conversaciones en una memoria a largo plazo?

2. Estado de los Datos: Si la respuesta es afirmativa y tienes acceso de lectura a esa capa de memoria, extrae y enlista aquí mismo toda la información consolidada que tienes sobre mí o sobre nuestras interacciones hasta este momento.

3. Transparencia: Si no cuentas con este mecanismo, o si el proceso ocurre en una capa de orquestación a la que no tienes acceso directo, indícalo de forma explícita y transparente en lugar de especular."

Referencia:
Base API URL https://api.nextgen-beta.ica.ttt.com/ica/v1
For CC, use https://api.nextgen-beta.ica.ttt.com/ica

{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.nextgen-beta.ica.ttt.com/ica",
    "ANTHROPIC_AUTH_TOKEN": "sk-_xxxx",
    "ANTHROPIC_MODEL": "claude-sonnet-5",
    "ANTHROPIC_SMALL_FAST_MODEL": "claude-haiku-4-5"
  },
  "model": "claude-sonnet-5",
  "modelSettings": {
    "claude-opus-5-5": {
      "effortLevel": "medium"
    },
    "opus": {
      "effortLevel": "low"
    },
    "claude-sonnet-5": {
      "effortLevel": "medium"
    }
  }
}