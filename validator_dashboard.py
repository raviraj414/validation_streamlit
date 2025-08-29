import streamlit as st
import html
from datetime import datetime, date, time, timedelta

from db import (
    get_commands_with_contexts,
    insert_dynamic_command,
    insert_static_command,
    update_last_processed_cmd,
    get_connection,  # used for history/details queries
)

# -------------------- Style (Light CSS) --------------------
_DEF_CSS = """
<style>
/* Headings */
.h-center { text-align:center; }

/* Badge pills for Dynamic/Static */
.badge {
  display:inline-block; padding:4px 10px; border-radius:12px;
  font-size:12px; font-weight:600; color:white;
}
.badge-dyn { background:#1f8e3d; }
.badge-stat{ background:#1a73e8; }

/* Zebra rows */
.row-wrap { padding:8px 10px; border-radius:8px; }
.row-wrap:nth-child(odd)  { background:#fafafa; }
.row-wrap:nth-child(even) { background:#f3f6fc; }

/* Table header */
.header-row {
  padding:10px 10px; border-radius:8px; background:#e9efff;
  font-weight:700;
}

/* Context panel */
.context-box {
  background-color:#f0f2f6; padding:20px 25px; border-radius:10px;
  border-left:6px solid #2c6ecb; min-height:150px; 
  box-shadow: 0 2px 5px rgba(0,0,0,0.08); overflow-x:auto;
}
.command-pre {
  background-color:#f5f5f5; padding:10px; border-radius:6px;
}
</style>
"""

# -------------------- Helpers & State --------------------
def _ensure_state():
    # Load data only when needed
    if "cmds_data" not in st.session_state:
        st.session_state.cmds_data = get_commands_with_contexts()
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
    if "sub_idx" not in st.session_state:
        st.session_state.sub_idx = {}

    # Navigation state: "dashboard" | "history"
    if "nav" not in st.session_state:
        st.session_state.nav = "dashboard"

    # History UI state
    if "history_filters" not in st.session_state:
        st.session_state.history_filters = {
            "use_date": False,       # only filter by date when True
            "date_range": None,      # (start_date, end_date)
            "command_id": "",
            "type": "All",           # All | Dynamic | Static
        }
    if "history_rows" not in st.session_state:
        st.session_state.history_rows = []
    if "history_selected" not in st.session_state:
        st.session_state.history_selected = None
    if "history_details" not in st.session_state:
        st.session_state.history_details = []
    if "history_mode" not in st.session_state:
        st.session_state.history_mode = "list"  # list | detail
    if "history_loaded" not in st.session_state:
        st.session_state.history_loaded = False  # to load all by default

def _set_nav(target: str):
    st.session_state.nav = target
    # when switching, reset history mode to list
    if target == "history":
        st.session_state.history_mode = "list"

def _navbar():
    # ⚠️ Update the logo path if needed
    try:
        st.sidebar.image("C:\\Users\\rtekale\\Downloads\\ptclogo.png", width=60)
    except Exception:
        pass

    st.sidebar.write(" ")

    # Navigation Buttons
    st.sidebar.button("📋 Dashboard", key="btn_nav_dashboard",
                      on_click=_set_nav, args=("dashboard",))
    st.sidebar.button("📜 History", key="btn_nav_history",
                      on_click=_set_nav, args=("history",))

    st.sidebar.write("---")
    if st.sidebar.button("🚪 Logout", key="btn_logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()

# -------------------- Data Access for History --------------------
def _user_table_name(base: str, user_id: int) -> str:
    if not isinstance(user_id, int):
        raise ValueError("user_id must be an integer")
    return f"{base}_{user_id}"

import streamlit as st
from db import get_connection

def render_history_for_user(user):
    st.markdown(f"🧑‍💻 Showing history for: {user['name']}")
    
    user_id = user["id"]
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Dynamic commands
    cursor.execute(f"""
        SELECT * FROM dynamic_cmds_user_{user_id}
        ORDER BY processed_time ASC
    """)
    dynamic_rows = cursor.fetchall()
    
    if dynamic_rows:
        st.markdown("🔥 Dynamic Commands")
        for row in dynamic_rows:
            cmd_id = row["id"]
            cmd_text = row["command_text"]
            proc_time = row["processed_time"].strftime("%Y-%m-%d %H:%M:%S")
            st.markdown(f"🟢 {cmd_id}: ~ {cmd_text}`` ⏱️ {proc_time}")
    else:
        st.info("No dynamic commands found.")

    # Static commands
    cursor.execute(f"""
        SELECT * FROM static_cmds_user_{user_id}
        ORDER BY processed_time ASC
    """)
    static_rows = cursor.fetchall()

    if static_rows:
        st.markdown("📦 Static Commands")
        for row in static_rows:
            cmd_id = row["id"]
            cmd_text = row["command_text"]
            proc_time = row["processed_time"].strftime("%Y-%m-%d %H:%M:%S")
            st.markdown(f"🟠 {cmd_id}: ~ {cmd_text}`` ⏱️ {proc_time}")
    else:
        st.info("No static commands found.")
    
    cursor.close()
    conn.close()


def fetch_user_history(
    user_id: int,
    start_dt: datetime | None,
    end_dt: datetime | None,
    cmd_id: int | None,
    action_type: str = "All"  # "All" | "Dynamic" | "Static"
):
    """
    Returns list of dict rows:
    { 'command_id': int, 'command_text': str, 'action': 'Dynamic'|'Static', 'processed_time': datetime }
    Ascending by command_id then processed_time.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        dyn_table = _user_table_name("dynamic_cmds_user", user_id)
        sta_table = _user_table_name("static_cmds_user", user_id)

        def where_parts():
            clauses = []
            params = []
            if start_dt:
                clauses.append("processed_time >= %s")
                params.append(start_dt)
            if end_dt:
                clauses.append("processed_time <= %s")
                params.append(end_dt)
            if cmd_id is not None:
                clauses.append("command_id = %s")
                params.append(cmd_id)
            return clauses, params

        dyn_clauses, dyn_params = where_parts()
        sta_clauses, sta_params = where_parts()

        dyn_where = f"WHERE {' AND '.join(dyn_clauses)}" if dyn_clauses else ""
        sta_where = f"WHERE {' AND '.join(sta_clauses)}" if sta_clauses else ""

        selects = []
        params_all = []

        if action_type in ("All", "Dynamic"):
            selects.append(f"SELECT command_id, command_text, 'Dynamic' AS action, processed_time FROM {dyn_table} {dyn_where}")
            params_all.extend(dyn_params)
        if action_type in ("All", "Static"):
            selects.append(f"SELECT command_id, command_text, 'Static'  AS action, processed_time FROM {sta_table} {sta_where}")
            params_all.extend(sta_params)

        if not selects:
            return []

        union_query = " UNION ALL ".join(selects)
        final_query = f"""
            {union_query}
            ORDER BY command_id ASC, processed_time ASC
            LIMIT 2000
        """
        cursor.execute(final_query, params_all)
        rows = cursor.fetchall()
        return rows
    except Exception as e:
        print("Error in fetch_user_history:", e)
        return []
    finally:
        cursor.close()
        conn.close()

def fetch_contexts_for_command(command_id: int):
    """
    Returns list of rows: [{'argument_id', 'command_id', 'full_command_line', 'context_lines'}]
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = """
            SELECT 
                a.id AS argument_id,
                c.id AS command_id,
                a.full_command_line,
                ctx.context_lines
            FROM commands c
            JOIN arguments a ON c.id = a.command_id
            LEFT JOIN contexts ctx ON ctx.argument_id = a.id
            WHERE c.id = %s
            ORDER BY a.id;
        """
        cursor.execute(query, (command_id,))
        results = cursor.fetchall()
        # Normalize context lines
        for row in results:
            ctx = row.get("context_lines")
            if ctx:
                row["context_lines"] = ctx.replace("\\n", "\n").replace("\\\\", "\\")
        return results
    except Exception as e:
        print("Error in fetch_contexts_for_command:", e)
        return []
    finally:
        cursor.close()
        conn.close()

# -------------------- History UI --------------------
def _history_list_view(user):
    st.markdown(_DEF_CSS, unsafe_allow_html=True)
    st.markdown("<h1 class='h-center'> Processing History</h1>", unsafe_allow_html=True)

    # Auto-load all history on first visit or after clear
    if not st.session_state.history_loaded:
        rows = fetch_user_history(user["id"], None, None, None, "All")
        st.session_state.history_rows = rows
        st.session_state.history_loaded = True

    # ----- Filters -----
    with st.expander(" Filters", expanded=True):
        col0, col1, col2, col3, col4 = st.columns([0.8, 1.2, 1.0, 1.0, 0.9])

        # Use date filter toggle
        use_date = col0.checkbox(
            "Use date",
            value=st.session_state.history_filters.get("use_date", False),
            
        )

        # Date range (defaults to last 7 days if enabled)
        default_start = date.today() - timedelta(days=7)
        default_end = date.today()
        current_dr = st.session_state.history_filters.get("date_range")
        date_range_val = col1.date_input(
            "Date range",
            value=(
                current_dr[0] if current_dr else default_start,
                current_dr[1] if current_dr else default_end
            ),
            help="Inclusive: start of day to end of day.",
            disabled=not use_date,
            key="history_date_range_input"
        )

        # Command ID filter
        command_id_input = col2.text_input(
            "Command ID",
            value=st.session_state.history_filters.get("command_id", ""),
            key="history_cmd_id_input"
        )

        # Type filter
        type_choice = col3.selectbox(
            "Type",
            options=["All", "Dynamic", "Static"],
            index=["All", "Dynamic", "Static"].index(st.session_state.history_filters.get("type", "All")),
            key="history_type_choice"
        )

        # Buttons
        apply_clicked = col4.button("Apply", key="btn_history_apply")
        clear_clicked = col4.button("Clear", key="btn_history_clear")

        if clear_clicked:
            # Reset filters to show ALL history immediately
            st.session_state.history_filters = {
                "use_date": False, "date_range": None, "command_id": "", "type": "All"
            }
            st.session_state.history_selected = None
            st.session_state.history_details = []
            st.session_state.history_mode = "list"
            st.session_state.history_loaded = True  # prevent auto reload loop
            st.session_state.history_rows = fetch_user_history(user["id"], None, None, None, "All")
            st.rerun()

        if apply_clicked:
            # Normalize inputs
            start_dt, end_dt = None, None
            if use_date and isinstance(date_range_val, tuple) and len(date_range_val) == 2 and date_range_val[0] and date_range_val[1]:
                start_dt = datetime.combine(date_range_val[0], time.min)
                end_dt = datetime.combine(date_range_val[1], time.max)

            cmd_id_val = None
            cmd_id_str = (command_id_input or "").strip()
            if cmd_id_str:
                if cmd_id_str.isdigit():
                    cmd_id_val = int(cmd_id_str)
                else:
                    st.warning("Command ID must be a number.")

            st.session_state.history_filters = {
                "use_date": use_date,
                "date_range": (
                    date_range_val[0], date_range_val[1]
                ) if (use_date and isinstance(date_range_val, tuple) and len(date_range_val) == 2) else None,
                "command_id": cmd_id_str,
                "type": type_choice,
            }

            rows = fetch_user_history(user["id"], start_dt, end_dt, cmd_id_val, type_choice)
            st.session_state.history_rows = rows
            st.session_state.history_selected = None
            st.session_state.history_details = []
            st.session_state.history_mode = "list"
            st.session_state.history_loaded = True
            st.rerun()

    rows = st.session_state.history_rows

    st.write("#### Actions")
    st.caption("Click **View details** on any row to preview the command and all its contexts.")
    
    h1, h2, h3, h4, h5 = st.columns([0.8, 3.0, 1.0, 1.6, 1.2])

# Shared styling for background and text
    cell_style = "background-color:#D3D3D3; color:black; padding:8px; border-radius:4px; text-align:center;"

    with h1:
        st.markdown(f"<div class='header-row' style='{cell_style}'>ID</div>", unsafe_allow_html=True)
    with h2:
        st.markdown(f"<div class='header-row' style='{cell_style}'>Command</div>", unsafe_allow_html=True)
    with h3:
    # No background or text color applied to "Type"
        st.markdown(f"<div class='header-row' style='{cell_style}'>Type</div>", unsafe_allow_html=True)
    with h4:
        st.markdown(f"<div class='header-row' style='{cell_style}'>Processed Time</div>", unsafe_allow_html=True)
    with h5:
        st.markdown(f"<div class='header-row' style='{cell_style}'>View details</div>", unsafe_allow_html=True)


    st.write("")

    if not rows:
        st.info("No history found. Apply filters or add activity.")
        return

    
    cell_style = "background-color:#D3D3D3; color:black; padding:8px; border-radius:4px; text-align:center;"
    for i, r in enumerate(rows):
        c1, c2, c3, c4, c5 = st.columns([0.8, 3.0, 1.0, 1.6, 1.2])
        with c1:
            st.markdown(f"<div class='row-wrap' style='{cell_style}'>{r['command_id']}</div>", unsafe_allow_html=True)

        with c2:
            st.markdown(
                f"<div class='row-wrap' style='{cell_style} white-space:nowrap; overflow:hidden; text-overflow:ellipsis;'>{html.escape(r.get('command_text', '') or '')}</div>",
                unsafe_allow_html=True
            )

        with c3:
            # Keep badge styling here for "Type" column
            badge_cls = "badge-dyn" if r["action"] == "Dynamic" else "badge-stat"
            st.markdown(f"<div class='row-wrap'><span class='badge {badge_cls}'>{r['action']}</span></div>", unsafe_allow_html=True)

        with c4:
            st.markdown(f"<div class='row-wrap' style='{cell_style}'>{r['processed_time']}</div>", unsafe_allow_html=True)
        with c5:
            if st.button("  View details", key=f"view_details_{i}_{r['command_id']}_{r['action']}"):
                # Store selection and load details; switch to detail mode
                st.session_state.history_selected = r
                st.session_state.history_details = fetch_contexts_for_command(r["command_id"])
                st.session_state.history_mode = "detail"
                st.rerun()

def _history_detail_view():
    """Renders the details view (hides filters and list)."""
    st.markdown(_DEF_CSS, unsafe_allow_html=True)

    # Back button
    if st.button("⬅ Back to History", key="btn_back_to_history"):
        st.session_state.history_mode = "list"
        st.rerun()

    sel = st.session_state.history_selected
    details = st.session_state.history_details

    if not sel:
        st.warning("No record selected.")
        return

    st.markdown("<h2>🔎 Details</h2>", unsafe_allow_html=True)

    # Selected record summary (only that command's data)
    st.markdown(f"**Command ID:** `{sel['command_id']}`")
    st.markdown(f"**Action:** `{sel['action']}`")
    st.markdown(f"**Processed at:** `{sel['processed_time']}`")

    # Command text from the action row
    st.markdown("**Command:**")
    st.code(sel.get("command_text") or "", language="bash")

    # Show context blocks grouped by argument
    if not details:
        st.warning("No contexts found for this command.")
        return

    st.markdown("**Context Lines (Grouped by Arguments):**")

    for idx, arg in enumerate(details, start=1):
        ctx_lines = arg.get("context_lines", "")
        if not ctx_lines.strip():
            continue

        clean_ctx = html.escape(ctx_lines.replace("\\n", "\n").replace("\\\\", "\\").strip())
        full_cmd = html.escape(arg.get("full_command_line", "") or "")

        st.markdown(
            f"""
            <div class="context-box">
                <div style="font-weight:600; margin-bottom:6px; color:#333;">🧾 Argument {idx}</div>
                <div style="margin-bottom:10px; color:black;"><strong>Full Command:</strong> <code>{full_cmd}</code></div>
                <div style="font-family:monospace; white-space:pre-wrap; word-wrap:break-word;
                            font-size:15px; color:black;">
                    {clean_ctx}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )


def _history_view(user):
    """Entry for History: route by mode."""
    if st.session_state.history_mode == "detail":
        _history_detail_view()
    else:
        _history_list_view(user)

# -------------------- Main Dashboard (existing) --------------------
def _dashboard_view(user):
    st.markdown("<h1 class='h-center'> Command Context Classifier</h1>", unsafe_allow_html=True)

    all_data = st.session_state.cmds_data
    grouped = {}
    for row in all_data:
        cmd_id = row["command_id"]
        grouped.setdefault(cmd_id, []).append(row)

    cmd_ids = list(grouped.keys())
    idx = st.session_state.current_index

    if idx >= len(cmd_ids):
        st.success("🎉 All commands reviewed!")
        return

    cmd_id = cmd_ids[idx]
    arg_list = grouped[cmd_id]

    sub_idx = st.session_state.sub_idx.get(cmd_id, 0)
    if sub_idx >= len(arg_list):
        sub_idx = 0

    argument = arg_list[sub_idx]

    st.markdown(f"### 🆔 Command ID: {cmd_id}")
    st.markdown(
        f"<pre class='command-pre'>{html.escape(argument['full_command_line'] or '')}</pre>",
        unsafe_allow_html=True
    )

    context = argument.get('context_lines') or "No context found."
    context_lines = context.splitlines()
    clean_context = "\n".join(line for line in context_lines)

    st.markdown(
    f"""
    <div class="context-box" style="background-color:#D3D3D3; padding:15px; border-radius:8px;">
        <h4 style="margin-top:0; margin-bottom:10px; color:black;">📄 Context Lines</h4>
        <div style="font-family:monospace; white-space:pre-wrap; word-wrap:break-word; 
                    font-size:15px; color:black;">
            {html.escape(clean_context)}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

    # Cycle through contexts for this command
    if st.button("➡️ Next Context", key=f"btn_next_ctx_{cmd_id}_{sub_idx}"):
        st.session_state.sub_idx[cmd_id] = (sub_idx + 1) % len(arg_list)
        st.rerun()

    # Action buttons
    col_dyn, col_stat = st.columns(2)

    with col_dyn:
        if st.button("✅ Mark as Dynamic", key=f"btn_mark_dyn_{cmd_id}_{sub_idx}"):
            insert_dynamic_command(user["id"], cmd_id, argument['full_command_line'])
            # NOTE: This uses the same index-based progression you already use
            update_last_processed_cmd(user["id"], idx + 1)
            st.session_state.current_index += 1
            st.rerun()

    with col_stat:
        if st.button("✅ Mark as Static", key=f"btn_mark_stat_{cmd_id}_{sub_idx}"):
            insert_static_command(user["id"], cmd_id, argument['full_command_line'])
            update_last_processed_cmd(user["id"], idx + 1)
            st.session_state.current_index += 1
            st.rerun()

    # Navigation between commands
    col1, col2 = st.columns([1, 1])

    with col1:
        if st.button("⬅️ Previous Command", key=f"btn_prev_cmd_{cmd_id}"):
            st.session_state.current_index = max(0, idx - 1)
            # Reset sub_idx for the new command view
            new_cmd_id = cmd_ids[st.session_state.current_index]
            st.session_state.sub_idx[new_cmd_id] = 0
            st.rerun()

    with col2:
        if st.button("➡️ Next Command", key=f"btn_next_cmd_{cmd_id}"):
            st.session_state.current_index = min(len(cmd_ids) - 1, idx + 1)
            new_cmd_id = cmd_ids[st.session_state.current_index]
            st.session_state.sub_idx[new_cmd_id] = 0
            st.rerun()

# -------------------- Entry --------------------
def validator_dashboard():
    user = st.session_state.get("user")
    if not user or user["role"].lower() != "validator":
        st.warning("Unauthorized or invalid role.")
        return

    _ensure_state()
    _navbar()

    if st.session_state.nav == "history":
        _history_view(user)
    else:
        _dashboard_view(user)
