<!-- Instructions partagées entre agents : la source de vérité est AGENTS.md. Ne rien dupliquer ici. -->
@AGENTS.md

## Claude Code notes

Only Claude-specific adaptations of `AGENTS.md` belong here.

- `AGENTS.md` mentions `apply_patch`: in Claude Code, use the `Edit` and `Write`
  tools for manual edits instead.
- When delegating to subagents, tell them to read `AGENTS.md` first; they do not
  inherit this conversation.
