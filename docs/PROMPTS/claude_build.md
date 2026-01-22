CLAUDE BUILD PROMPT (PASTE THIS AS ONE BLOCK)

You are Claude Code operating inside a git repo on a private NUC (Docker). Build a production-lean Django+Postgres system that:
- Uses Google Sheets/Form responses as the UI (staff keep using Sheets)
- Pulls sheet rows on a schedule (no inbound push/webhooks)
- Stores Bronze (append-only raw truth), produces Silver (normalized staging), promotes to Gold (canonical entities/events)
- Implements matching between Shred Log and Drive Removal Log as a first-class product, including explicit "doesn't match" outputs
- Includes pgAdmin with the Postgres server pre-registered on startup
- Uses Google Workspace Service Account credentials (sheets are shared to the service account email)

Your job is to implement the stack + code + tests so it can be rebuilt from empty DB and verified deterministically.

[Full prompt content as provided in the document]
