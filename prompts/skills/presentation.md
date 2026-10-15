# Terminal reply presentation

Use `present_reply` exactly once, as the last tool call of this run, after
all domain tools required by the user's request have completed. Call it on
its own, never in the same batch as another tool. It ends the run immediately;
there is no later background work or follow-up after this call.

This tool only presents a reply. It never reads lists, searches personal data,
creates a proposal, writes a task or sends confirmation buttons.

- To answer "¿Qué listas tengo?", first call `list_todo_lists` and wait for
  its result, then present the verified lists in `answer`.
- To answer "¿Qué tengo en la lista Casas?", resolve the list using
  `list_todo_lists` if necessary, then call `list_todo_items` with its actual
  ID. Present its verified tasks, or a clarification if no unique match exists.
- To handle "Crea una lista Casa", first call `propose_todo_list(name="Casa")`.
  Only after it succeeds, put a short proposal narration in `proposal_text`.
  The Core renders the stored proposal and its Sí/No buttons.
- For greetings, general questions or a necessary clarification, no domain
  tool is needed: use `answer` directly and leave `proposal_text` empty.
- For mixed requests keep the read answer, verified trivial results and
  necessary safety warnings in `answer`; put only reviewable proposal
  narration in `proposal_text`.
- Tool failures and missing information belong in `answer`, not in
  `proposal_text`. Never claim that a failed tool succeeded.

Do not finish with "Déjame consultar", "Voy a buscar", "Necesito localizar"
or any other promise to do the requested work later. Call the required domain
tools now instead. Never invent data, proposal creation or completion. A
non-empty sentence is not evidence that an action happened.

Return plain Spanish Markdown in both arguments. At least one must contain
text. Never copy a pending proposal's fields or a confirmation request into
`answer`; the Core owns that presentation. A proposal narration without an
actual stored proposal is not deliverable. Do not expose the tool's internal
JSON result to the user.