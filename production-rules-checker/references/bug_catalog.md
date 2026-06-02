# Bug Catalog — regression rules and their incidents

Every regex rule in `validate_production_rules.py` that begins with a date
comment maps to a real production incident. Removing a rule requires removing
its row from this file (and explaining what observability or test replaced it).

| Date | Rule | Incident | Files where the bug lived | What fixed it |
|------|------|----------|----------------------------|---------------|
| 2026-05-28 | NO_FABRICATED_FALLBACK_STRINGS | `test@abc.com` saw "Meeting on May 28, 2026" rows for both failed and still-processing sessions. Backend fabricated the title from `created_at` when `summary_title` was empty, so the iOS app could not distinguish completed from failed. | `KK_frontendmobile/KK_frontendios/{klik_api,transformers}.py` | Killed the fallback. Added `status` to `MeetingDto`. iOS now renders state explicitly. |
| 2026-05-28 | NO_SINGLE_CODE_RETRY_CLASSIFIER | ASR retry only fired for Volcengine `55001010`. Volcengine actually returned `45000006` for the same class of failure. No retry → user sees Recording failed. | `KK_asr/core/volcengine_transcriber.py:204` | Replaced the single `_AUDIO_DOWNLOAD_TIMEOUT_STATUS` string with a tuple of codes plus matching error markers. |
| 2026-05-28 | NO_SILENT_RETRY_SCHEDULE_FAILURE | Orchestrator scheduled `asyncio.create_task(_delayed_retry())` from inside a FastAPI `BackgroundTasks` threadpool worker → `RuntimeError("no running event loop")` → `except Exception: logger.warning(retry_schedule_failed)` → retry NEVER fired in production, the warning was ignored. | `KK_orchestrator/orchestrator_api.py:2041` | Replaced with `threading.Timer` daemon. Future variants of "warning on retry-fail" are now linted. |
| 2026-05-28 | NO_UNGUARDED_PYDANTIC_FROM_LLM | `MeetingMinutes(...)` Pydantic build sat OUTSIDE the LLM try/except. LLM occasionally returns `speakers=[None]`, Pydantic raises `ValidationError`, FastAPI returns bare 500 with no structured log. | `KK_meeting_minutes/meeting_minutes_api.py:234-300` | Wrapped construction in try/except that logs `minutes_response_build_failed` with the LLM payload keys. Also sanitised None entries. |

## How this catalog is updated

Whenever a production bug fix lands on `main`, the SessionEnd hook (see
`~/.claude/settings.json`) fires a reminder to add a row here and a regex rule
to `validate_production_rules.py`. The reminder is NOT optional — silent bugs
are how we end up debugging the same shape twice.
