# AncoraMind — Condiciones del piloto de pruebas

> Documento para las personas invitadas al piloto. Es el destino de
> `PILOT_NOTICE_URL`. Última actualización: 2026-10-20.

## Qué es esto

AncoraMind es un asistente personal en Telegram que guarda notas, documentos,
datos de vehículos, recordatorios, eventos y listas de tareas. Este piloto es una
**prueba técnica a título personal**, con muy pocas personas y durante unos días
o semanas. No es un servicio comercial ni ofrece garantías de disponibilidad.

## Lo más importante: usa solo datos ficticios

**No escribas ni subas información real.** Inventa todo lo que le cuentes al bot:
nombres, matrículas, direcciones, documentos, fechas y notas. Esto incluye
documentos, fotos y PDF: usa solo ejemplos de prueba.

Si por error compartes un dato real, avisa a quien te invitó cuanto antes.

## Qué ocurre con lo que escribes

Tus mensajes y archivos pasan por estos servicios:

| Servicio | Para qué se usa |
|---|---|
| Telegram | Canal de conversación con el bot |
| Railway | Aloja la aplicación del asistente |
| Supabase | Base de datos y almacenamiento de documentos |
| OpenRouter y el modelo de IA que atiende la petición | Entender tu mensaje y responder |
| Grafana Cloud | Métricas técnicas de funcionamiento, sin contenido de tus mensajes |

El texto de tus mensajes y el contenido de tus documentos se envían al modelo de
IA para generar la respuesta. **No se ha verificado** que los proveedores del
modelo no conserven esos datos ni que no los usen para otros fines. Por eso
insistimos en los datos ficticios.

## Cómo funciona el asistente

- Eres atendido por una IA y puede equivocarse. Revisa sus respuestas.
- Para guardar o cambiar datos importantes, el asistente te pide confirmación.
  Las notas y los cambios simples de tareas se guardan sin pedirla, pero quedan
  registrados.
- Solo funciona en chat privado con el bot.
- Comandos útiles: `/help` muestra la ayuda y `/new` empieza una conversación
  nueva sin borrar tu memoria.

## Conservación y borrado

- Los datos que introduzcas se conservan mientras dure el piloto. Al ser ficticios,
  **no se prevé un borrado planificado**.
- Los datos de conversación que quedan en un estado de error ambiguo se eliminan
  automáticamente a los 7 días, conservando solo metadatos técnicos.
- Tu acceso puede revocarse en cualquier momento, tuyo o del operador, y deja de
  funcionar en tu siguiente mensaje.

## Qué no cubre este piloto

Al ser una prueba cerrada con datos ficticios, **quedan fuera de alcance** y se
reconocen como trabajo futuro antes de cualquier uso real o abierto:

- Revisión legal de bases jurídicas y roles de tratamiento (RGPD).
- Contratos de encargado de tratamiento con proveedores y revisión de
  transferencias internacionales.
- Evaluación de impacto (DPIA) y procedimiento de notificación de incidentes.
- Procedimientos verificados de acceso, rectificación, supresión y exportación.
- Clasificación y obligaciones del Reglamento europeo de IA.
- Notas de voz: el piloto no las contempla.

Que estos puntos estén fuera de alcance es precisamente la razón por la que el
piloto solo admite datos ficticios.

## Contacto y retirada

Para dejar el piloto, pedir que se revoque tu acceso o preguntar cualquier duda,
escribe a la persona que te envió la invitación.
