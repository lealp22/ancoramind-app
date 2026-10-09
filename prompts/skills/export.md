# Skill — Export to PDF

## When to Use

- User explicitly asks for a document/PDF of something already discussed:
  - "Pásamelo en PDF"
  - "Mándame esa lista como documento"
  - "Exporta este resumen a PDF"
  - "¿Me lo puedes dar en un fichero?"
- Never call it to "share" something the user did not ask to receive as a
  file — a normal chat answer is the default.

## How to Use It

`export_document` only renders and sends — it never fetches data on its
own. Compose the Markdown yourself first:

1. If exporting something canonical (a note, a TODO list, a vehicle's
   maintenance history), call the matching read tool first
   (`search_notes`, `list_todo_items`, etc.) and format its result as
   Markdown — headings, lists, tables as needed.
2. Call `export_document(markdown_text, title=...)` with that Markdown.
   Give it a short, descriptive `title` when you can — it becomes both the
   PDF's heading and (sanitized) its filename.
3. Relay the tool's own confirmation to the user; do not invent your own
   "I've sent you a PDF" before the tool actually confirms it.

No confirmation step is required before calling it — unlike WRITE
mutations, exporting creates no canonical data and reaches only the
requesting user. Content is bounded; if the tool reports the content was
too long or the render failed, say so plainly and suggest a shorter export
rather than retrying blindly.
