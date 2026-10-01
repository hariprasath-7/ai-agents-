# Telegram AI Task Manager Agent — V2 Progress Summary

### 1. Temporal Engine & Database Expansion (Phase 1)

- **Schema Migration:** Added `due_date` (TIMESTAMPTZ, nullable) and `reminded`
  (BOOLEAN, default False) columns to the PostgreSQL `todos` table with automated
  idempotent startup execution (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`).
- **Dynamic Temporal Context:** Injected UTC timestamp and IST offset into the
  LLM system prompt dynamically, allowing Gemini to accurately resolve relative
  natural language deadlines ("tomorrow 5 PM", "in 2 minutes").
- **Date-Aware Tooling:**
  - Extended `add_todo` and `update_task` to parse ISO-8601 timestamps.
  - Updated task creation receipts and list views to conditionally format and
    display deadlines (`Due: DD MMM YYYY, HH:MM`).

### 2. Autonomous Background Push Worker (Phase 1)

- **Custom Async Poller (asyncio background task in lifespan):** Implemented
  `check_reminders_loop` integrated into FastAPI lifespan context, checking
  every 30 seconds for pending overdue tasks
  (`due_date <= NOW() AND status = 'pending' AND reminded = FALSE`).
- **Autonomous Push Notifications:** Dispatches proactive Telegram alerts with
  priority indicators directly to the user's chat when a deadline expires.
- **State Guarantee:** Automatically flips `reminded = True` on successful push
  dispatch to eliminate duplicate alert spam.

### 3. Interactive Inline Buttons & Callbacks (Phase 2)

- **Inline Keyboard Layout:** Created `build_task_keyboard(task_id)` attaching
  action buttons to reminder alerts:
  - `[ ✅ Done ]` | `[ ⚡ High ]`
  - `[ ⏰ Snooze 10m ]` | `[ 🗑️ Delete ]`
- **Low-Latency Callback Engine:** Added Telegram `callback_query` webhook
  router:
  - Bypasses LLM inference completely for button clicks, executing direct
    database mutations in milliseconds.
  - Supports 10-minute task snoozing (`snooze:10:{id}`), priority toggles
    (`prio:high:{id}`), completion (`done:{id}`), and deletion (`del:{id}`).
  - Provides Telegram `answerCallbackQuery` toast notifications and updates the
    original message receipt in chat.

### 4. Next Planned Milestones

- **Phase 4:** Cloud Deployment (Docker containerization on Render/Railway,
  persistent webhooks, 24/7 uptime).
- **List-View Interactivity:** Attaching inline action controls directly under
  general task listing queries.