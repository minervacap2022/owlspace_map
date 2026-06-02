# KLIK Production Rules - Complete Reference

Authoritative reference for all production code rules.
Applies to both Python (.py) and Kotlin (.kt) code.

## Sources of Truth (KLIK 开发规范 wiki)

These rules are the machine-checkable enforcement of the team standards registry. When the wiki
and this file disagree, **the wiki wins** — update this file to match (规范跟代码同源):

- **KLIK 开发规范** (standards index): https://qcnyyz11v8oe.feishu.cn/wiki/X7WVwNea4i4kavkF8e9cUcs8nqg
- **KLIK 错误码注册表** (error-code Base `WY9lbE27ya3oTesLf7CcZ3NAnch`): https://qcnyyz11v8oe.feishu.cn/wiki/I7XqwORteiMUdyk4DtJcBwWrntg → Rules 14 & 15.
- **KLIK 分层架构与服务管理说明** (layering · systemd · klik-infra · Alembic): https://qcnyyz11v8oe.feishu.cn/wiki/R72lwdCgKiV6QXkqA8ncNXGcnjf → Rule 13.

## Rule 1: NO ENV FILES

**Rationale**: Environment variables must be pre-loaded by shell/systemd/supervisor. Code must not load .env files.

### Forbidden

```python
# ❌ Python
from dotenv import load_dotenv
load_dotenv()
import dotenv

# ❌ Bash
source .env
source /path/to/.env
```

### Correct

```python
# ✅ Python - fail-fast on missing
db_host = os.environ["POSTGRES_HOST"]

# ✅ Python - use settings
from KK_common.config import settings
db_host = settings.postgresql.host
```

```bash
# ✅ Bash - fail-fast
: "${POSTGRES_HOST:?Missing POSTGRES_HOST}"
```

---

## Rule 2: NO HARDCODED VALUES

**Rationale**: All paths, hosts, ports, secrets must come from configuration.

### Forbidden

```python
# ❌ Hardcoded paths
output_dir = "/root/KK_logs"
data_path = "/home/chengyi/data"

# ❌ Hardcoded hosts
host = "localhost"
host = "127.0.0.1"
```

```kotlin
// ❌ Hardcoded secrets
private const val API_KEY = "sk-REDACTED-EXAMPLE-DO-NOT-USE"
private const val API_ENDPOINT = "https://dashscope.aliyuncs.com/api/..."

// ❌ Debug flags
const val IS_DEBUG_MODE = true
```

### Correct

```python
# ✅ From environment
output_dir = os.environ["KK_LOGS_DIR"]
```

```kotlin
// ✅ From Environment config
val endpoint = ApiConfig.ALIYUN_ASR_ENDPOINT
val apiKey = ApiConfig.ALIYUN_ASR_API_KEY
```

### Exceptions

- `ports.md` - documentation of port assignments
- `CLAUDE.md` - documentation
- `Environment.kt` / `ApiConfig.kt` - the config sources themselves
- Test assertions comparing expected values

---

## Rule 3: NO FALLBACKS / DEFAULTS

**Rationale**: Missing configuration must fail immediately, not silently use defaults.

### Forbidden

```python
# ❌ getenv with default
api_key = os.getenv("API_KEY", "default-key")
host = os.environ.get("HOST", "localhost")

# ❌ Silent exception handling
try:
    risky_operation()
except Exception:
    pass
```

```kotlin
// ❌ runCatching that absorbs errors
val result = runCatching { parse(data) }.getOrElse { emptyList() }

// ❌ Empty catch blocks
catch (_: Exception) {}

// ❌ Fallback/degradation comments
// Fallback: use a fresh NativeHttpClient
// Best-effort: try again silently
// Graceful degradation
```

### Correct

```python
# ✅ Fail-fast
api_key = os.environ["API_KEY"]  # Raises KeyError
```

```kotlin
// ✅ Explicit error handling
try {
    parse(data)
} catch (e: JsonDecodingException) {
    throw Exception("Failed to parse response: ${e.message}")
}
```

---

## Rule 4: NO MOCK/FAKE/TRUNCATED DATA

**Rationale**: Production code must use real data paths and full data.

### Forbidden in Production Code

```python
# ❌ Mock/fake data
mock_response = {"status": "ok"}
fake_user = User(id=1, name="Test")
```

```kotlin
// ❌ Mock references in error messages
message = "Network not available. Using mock data."

// ❌ Placeholder logic
// In production, use platform-specific clipboard API
// For now, just acknowledge the action
```

---

## Rule 5: NO BACKWARD COMPATIBILITY

**Rationale**: Old code must be deleted, not shimmed.

### Forbidden

```python
# ❌ Legacy code
legacy_handler = old_function
_deprecated_method()
```

```kotlin
// ❌ Deprecated annotations in production
@Deprecated("Use newFunction()")
fun oldFunction() { ... }

// ❌ Suppress deprecation warnings
@Suppress("DEPRECATION")
```

---

## Rule 6: NO COMPATIBILITY / PATCH SOLUTIONS (不允许兼容性或补丁性方案)

**Rationale**: Solutions must address root cause. No shims, workarounds, or temporary patches.

### Forbidden

```kotlin
// ❌ Temporary fixes
// temp fix for crash
// temporary workaround
// HACK: bypass validation

// ❌ Compatibility shims
backwardCompatMapping()
legacyConverter()
```

### Correct

```kotlin
// ✅ Fix the root cause
// ✅ Delete old code path, implement new one directly
```

---

## Rule 7: NO OVERENGINEERING (不允许过度设计，保持最短路径实现)

**Rationale**: Build for now, not for hypothetical futures. Minimum viable implementation.

### Forbidden

```kotlin
// ❌ Abstractions for single implementations
interface PaymentStrategy { ... }
class CreditCardStrategy : PaymentStrategy { ... }
// Only one strategy exists

// ❌ Future-oriented TODOs
// TODO: eventually support multiple providers
// TODO: add caching layer later

// ❌ Feature flags in production
if (FeatureFlags.newDesign) { ... }
```

### Correct

```kotlin
// ✅ Direct implementation
fun processPayment(card: CreditCard) { ... }

// ✅ Implement what's needed now, nothing more
```

---

## Rule 8: NO UNSOLICITED FALLBACK SOLUTIONS (不允许自行给出需求以外的兜底和降级方案)

**Rationale**: Only implement what was requested. Do not add fallbacks, degradation, or alternative paths that were not part of the requirement. These cause business logic drift.

### Forbidden

```kotlin
// ❌ Silent error absorption
runCatching { fetchData() }.getOrElse { emptyList() }
catch (_: Exception) {}

// ❌ "In production" comments revealing unimplemented code
// In production, call clear history use case
// For now, just acknowledge the action

// ❌ Best-effort patterns
// best-effort push token registration
```

### Correct

```kotlin
// ✅ Fail explicitly
val data = fetchData()  // Let it throw

// ✅ Implement the actual logic
chatRepo.clearChatHistory()
```

---

## Rule 9: FULL-CHAIN CORRECTNESS (全链路逻辑必须正确)

**Rationale**: Every code path must be complete. No TODO() bombs, no empty function bodies, no stub implementations that will crash at runtime.

### Forbidden

```kotlin
// ❌ Runtime bombs
TODO()
throw NotImplementedError()
throw UnsupportedOperationException()

// ❌ Empty function bodies
override fun onResume() {}
suspend fun fetchData() {}
```

### Correct

```kotlin
// ✅ Complete implementation
override fun onResume() {
    refreshData()
}
```

---

## Rule 10: KK_common/logger USAGE (Python only)

**Rationale**: All logging must use ECS-compliant LogManager.

### Correct

```python
from KK_common.logger import LogManager
logger = LogManager.setup_logging("KK_exec", "api.routes")
```

---

## Rule 11: UV WORKSPACE COMPLIANCE (Python only)

**Rationale**: All modules managed via UV workspace. No sys.path hacks.

---

## Rule 12: USER-SPECIFIC DATA ISOLATION

**Rationale**: All data access must be scoped to user_id.

---

## Rule 13: SERVICE & INFRASTRUCTURE TOPOLOGY (systemd / klik-infra / Alembic)

**Source of truth**: wiki "KLIK 分层架构与服务管理说明". The stack is three layers across two repos —
infrastructure (**klik-infra**: Postgres/Redis/PgBouncer, schema, migrations, backup), application
(**klik-app** `KK_*` business code), and deploy/ops (**klik-app `deploy/`**, systemd).

### Forbidden

```bash
# ❌ Managing services the old way — SUPERSEDED by systemd
restart_all.sh              # survives ONLY as a rollback path, never the way to add/manage a service
restart_auth.sh             # per-service restart scripts — gone
klik-watchdog.sh            # polling keep-alive — replaced by systemd Restart=always
```

```python
# ❌ Raw schema DDL in application code — schema lives in klik-infra/Alembic
cursor.execute("CREATE TABLE ...")
cursor.execute("ALTER TABLE ...")

# ❌ DB deploy details embedded in KK_* app code
DB_PASSWORD = "..."          # app knows only a connection ADDRESS
```

### Correct

```bash
# ✅ Add a service: drop deploy/services/<svc>.env (WORKDIR / PORT / EXEC), then:
sudo deploy/scripts/install-systemd.sh   # no new unit, no new restart script

# ✅ Manage a service
systemctl restart klik@<svc>             # one service
systemctl restart klik.target            # whole stack
journalctl -u klik@<svc> -f              # logs

# ✅ Change DB schema: edit the model, generate an Alembic revision in klik-infra.
#    Migrations connect to the DIRECT Postgres port 5432, NOT PgBouncer 6432
#    (transaction pooling breaks multi-statement DDL).

# ✅ Bring up the DB locally via klik-infra docker compose — never hand-install Postgres.
```

---

## Rule 14: ERROR CODE & WIRE FORMAT COMPLIANCE

**Source of truth**: `docs/error-codes.md` in the Klik backend repo + the **KLIK 错误码注册表** Feishu Base (`WY9lbE27ya3oTesLf7CcZ3NAnch`). A code may be used in production only when it is **registered AND `status=active`** in both (a `proposed` code is not yet usable). Codes are 5-char `<Source><CC><SS>`; `has_stack_trace=true` only for `B02xx` (see Rule 15).

**Rationale**: All error responses must carry a registered 5-char KLIK error code and follow the standard wire envelope. Ad-hoc plain strings leak internal details and break client-side error handling.

### Format

Error code: `<Source><CC><SS>` — exactly 5 characters.

| Source | Meaning |
|--------|---------|
| A | Caller error (params, auth, quota) |
| B | Our error (internal, DB, config) |
| C | Third-party error (HTTP, network, rate limit) |

### Wire format (all failure responses)

```json
{
  "error": {
    "error_code":    "A0201",
    "error_message": "param validation failed: 'tz' is not a valid IANA timezone",
    "user_tip":      "调用参数不合法。",
    "stack_trace":   ""
  }
}
```

### Forbidden

```python
# ❌ Plain string detail — bypasses wire format
raise HTTPException(status_code=400, detail="invalid timezone")

# ❌ Non-standard error code
return {"error": {"error_code": "INVALID_TZ", ...}}

# ❌ Ad-hoc shorthand
return {"error": "auth_failed"}
```

### Correct

```python
# ✅ Standard wire format via JSONResponse
from fastapi.responses import JSONResponse

return JSONResponse(status_code=400, content={"error": {
    "error_code":    "A0103",
    "error_message": f"Invalid timezone: {tz}",
    "user_tip":      "时区参数无效，请传入合法的 IANA 时区名称。",
    "stack_trace":   "",
}})
```

### Registering a new code

1. Check `docs/error-codes.md` — does a matching code exist?
2. If not: add to the Feishu Base (status=proposed), add to `docs/error-codes.md`, PR.
3. Use the code in code only after both are merged.

---

## Rule 15: STACK TRACE DISCIPLINE

**Rationale**: `stack_trace` in the wire format is ONLY for `B02xx` (internal/panic) errors. Filling it for auth errors, param errors, or upstream errors leaks internals and misleads oncall.

### Forbidden

```python
# ❌ stack_trace outside B02xx
return JSONResponse(content={"error": {
    "error_code": "C0101",
    ...
    "stack_trace": traceback.format_exc(),  # WRONG — only B02xx
}})
```

### Correct

```python
# ✅ B02xx — stack trace allowed
return JSONResponse(status_code=500, content={"error": {
    "error_code":  "B0201",
    "error_message": str(exc),
    "user_tip":    "服务内部异常,我们已记录此问题。",
    "stack_trace": traceback.format_exc(),
}})

# ✅ All other codes — stack_trace = ""
return JSONResponse(status_code=400, content={"error": {
    "error_code":  "A0103",
    "error_message": f"Invalid timezone: {tz}",
    "user_tip":    "时区参数无效。",
    "stack_trace": "",
}})
