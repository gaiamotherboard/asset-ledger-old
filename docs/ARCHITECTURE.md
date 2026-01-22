# Architecture

## System Overview

Asset Ledger is a production-lean Django+Postgres system that tracks IT asset lifecycles using Google Sheets as the UI. It implements a Bronze/Silver/Gold data architecture with explicit matching between drive removals and shreds.

## Design Principles

### 1. Pull-Only Architecture
- The NUC is not publicly exposed
- No inbound internet connections required
- System polls Google Sheets on a schedule (default: every 15 minutes)
- Uses Google Workspace Service Account for authentication

### 2. Bronze/Silver/Gold Layers

#### Bronze (Append-Only Truth)
- **Table**: `ingest_event`
- Raw data as ingested from source systems
- Append-only: never delete or update in normal operation
- Idempotency via unique constraint on `(source_system, source_sheet_id, source_tab, source_row_key, payload_hash)`
- Edits to source rows create new bronze records with different `payload_hash`

#### Silver (Normalized Staging)
- **Tables**: `stg_shred_serial`, `stg_drive_removal`
- Normalized data with validation
- One staging record per bronze `IngestEvent` (1:1 FK)
- Serial normalization: trim → uppercase → strip trailing punctuation
- Validation errors recorded but don't block processing
- Invalid records remain in silver but don't promote to gold

#### Gold (Canonical Entities)
- **Tables**: `drive`, `batch`, `drive_event`, `match_decision`
- Canonical entities and lifecycle events
- Upsert pattern for entities (drives, batches)
- Events are immutable with provenance to bronze
- Idempotent promotion via unique constraints

### 3. Matching as a First-Class Product

Matching between drive removals and shreds is not a side effect—it's an explicit output:

**MatchDecision Table** records every matching decision:
- `MATCH`: Exactly 1 removal + 1 shred for a serial (confidence 1.0)
- `NO_MATCH`: Drive has only removal OR only shred (confidence 0.0)
- `AMBIGUOUS`: Multiple candidates for matching (confidence 0.5)

**Rule Versioning**: `rule_version` field enables algorithm evolution
- Current: `strict_serial_v1`
- Future: Could add fuzzy matching, time-based rules, etc.

**Explainability**: Every decision has a `reason` field

## Data Flow

```
Google Sheets (UI)
       ↓
[pull_sheets command] ← runs every 15 min
       ↓
Bronze Layer (IngestEvent)
       ↓
[pipeline_run: stage]
       ↓
Silver Layer (StgShredSerial, StgDriveRemoval)
       ↓
[pipeline_run: promote]
       ↓
Gold Layer (Drive, Batch, DriveEvent)
       ↓
[pipeline_run: match]
       ↓
Match Decisions
       ↓
SQL Views (reporting surface)
```

## Google Sheets Access Model

### Service Account Authentication
- Uses a Service Account JSON key file
- Sheets are shared to the service account email address
- No domain-wide delegation required
- Read-only access (`spreadsheets.readonly` scope)

### Configuration
- `LEDGER_SHEETS_CONFIG` environment variable (JSON array)
- Each sheet config specifies: name, sheet_id, tab, header_row
- Example:
  ```json
  [
    {"name":"shred_log_serials","sheet_id":"SHEET_ID","tab":"Form Responses 1","header_row":1},
    {"name":"drive_removal_log","sheet_id":"SHEET_ID","tab":"Form Responses 1","header_row":1}
  ]
  ```

## Database Schema

### Bronze
- `ingest_event`: All raw ingestion events

### Silver
- `stg_shred_serial`: Normalized shred log entries
- `stg_drive_removal`: Normalized drive removal entries

### Gold
- `drive`: Canonical drive entities (keyed by normalized serial)
- `batch`: Shred batch entities
- `drive_event`: Lifecycle events (REMOVED, SHREDDED)
- `match_decision`: Matching decisions

### Views
- `v_drive_lifecycle`: Complete lifecycle per drive
- `v_unmatched_removals`: Removals without matching shreds
- `v_unmatched_shreds`: Shreds without matching removals
- `v_ambiguous_matches`: Drives with ambiguous matching

## Idempotency Guarantees

1. **Bronze**: Unique constraint prevents duplicate ingestion
2. **Silver**: OneToOne FK to bronze ensures 1 staging record per source event
3. **Gold**: 
   - DriveEvent: Unique on `(source_event, event_type)`
   - MatchDecision: One decision per drive per rule version
4. **Pipeline**: Can be run repeatedly without duplicating data

## Security & Secrets

- **Never committed**: `secrets/google_sa.json`, `secrets/pgpassfile`, `.env`
- **Database**: Not exposed to network (internal Docker network only)
- **pgAdmin**: Bound to localhost only (127.0.0.1:5050)
- **Django Admin**: Accessible on LAN via port 8000 (secured by SSH/ZeroTier)

## Scalability Considerations

Current design targets:
- Thousands of drives per year
- Hundreds of ingestion events per day
- Pull interval: 15 minutes (configurable)

For higher volume:
- Increase `PULL_INTERVAL_SECONDS`
- Add database indexes as needed
- Consider archiving old bronze records

## Extension Points

1. **New Source Systems**: Add new `source_system` types in bronze
2. **New Staging Tables**: Add new Silver tables for new entity types
3. **New Matching Rules**: Increment `rule_version` and add logic
4. **New Views**: Add SQL views via migrations
5. **Webhooks**: Could add webhook receiver if inbound access becomes available
