# Command Service Layer

Services are shared command logic for both `bot/module/` text commands and
`bot/slash/` app commands.

Rules:

- Services may validate input, query/update the database, mutate Discord objects,
  and call external APIs.
- Services must not send Discord messages, open modals, prompt users, or import
  from `bot.module` or `bot.slash`.
- Text and slash cogs remain responsible for parsing input, permission
  decorators, prompts, modals, confirmations, pagination, and sending responses.
- Text command behavior is the reference behavior when slash and text flows
  differ.

Migration checklist for each command family:

- Move duplicated validation and state changes into a service.
- Move duplicated embed/page construction into `bot/presenters/` when useful.
- Leave text-only and slash-only interaction details in their cog.
- Run `python3 -m py_compile` and `git diff --check` on touched files.

