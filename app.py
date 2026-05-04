import re
import streamlit as st
from datetime import date
import pawpal_ai as pai
import pawpal_system as ps

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# ---------------------------------------------------------------------------
# Service initialisation — stored in session_state so they (and their
# class-level data dicts) survive across Streamlit reruns.
# ---------------------------------------------------------------------------
if "user_service" not in st.session_state:
    st.session_state.user_service = ps.UserService()
if "pet_service" not in st.session_state:
    st.session_state.pet_service = ps.PetService()
if "care_target_service" not in st.session_state:
    st.session_state.care_target_service = ps.CareTargetService()
if "activity_service" not in st.session_state:
    st.session_state.activity_service = ps.ActivityService()
if "care_score_service" not in st.session_state:
    st.session_state.care_score_service = ps.CareScoreService(
        st.session_state.activity_service,
        st.session_state.care_target_service,
    )
if "task_service" not in st.session_state:
    st.session_state.task_service = ps.TaskService()
if "ai_coach" not in st.session_state:
    st.session_state.ai_coach = pai.PawPalAICoach(
        st.session_state.pet_service,
        st.session_state.care_target_service,
        st.session_state.activity_service,
        st.session_state.care_score_service,
        st.session_state.task_service,
    )
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "selected_pet_id" not in st.session_state:
    st.session_state.selected_pet_id = None
if "last_ai_plan" not in st.session_state:
    st.session_state.last_ai_plan = None
if "last_ai_plan_pet_id" not in st.session_state:
    st.session_state.last_ai_plan_pet_id = None
if "ai_last_apply_result" not in st.session_state:
    st.session_state.ai_last_apply_result = None

us   = st.session_state.user_service
ps_  = st.session_state.pet_service
cts  = st.session_state.care_target_service
acts = st.session_state.activity_service
css  = st.session_state.care_score_service
ts   = st.session_state.task_service
ai_coach = st.session_state.ai_coach

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🐾 PawPal+")

# ---------------------------------------------------------------------------
# Auth — shown when no user is logged in
# ---------------------------------------------------------------------------
if st.session_state.current_user is None:
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_register:
        st.subheader("Create Account")
        reg_name     = st.text_input("Name",     key="reg_name")
        reg_email    = st.text_input("Email",    key="reg_email")
        reg_password = st.text_input("Password", key="reg_password", type="password")
        if st.button("Register"):
            if not reg_name or not reg_email or not reg_password:
                st.error("All fields are required.")
            else:
                try:
                    user = us.register(reg_name, reg_email, reg_password)
                    st.session_state.current_user = user
                    st.success(f"Welcome, {user.name}!")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    with tab_login:
        st.subheader("Login")
        login_email    = st.text_input("Email",    key="login_email")
        login_password = st.text_input("Password", key="login_password", type="password")
        if st.button("Login"):
            try:
                user = us.login(login_email, login_password)
                st.session_state.current_user = user
                st.success(f"Welcome back, {user.name}!")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

    st.stop()

# ---------------------------------------------------------------------------
# Logged-in header
# ---------------------------------------------------------------------------
user = st.session_state.current_user
col_user, col_logout = st.columns([5, 1])
with col_user:
    st.markdown(f"**{user.name}** &nbsp;·&nbsp; {user.email}")
with col_logout:
    if st.button("Logout"):
        st.session_state.current_user    = None
        st.session_state.selected_pet_id = None
        st.session_state.last_ai_plan = None
        st.session_state.last_ai_plan_pet_id = None
        st.session_state.ai_last_apply_result = None
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Top-level navigation
# ---------------------------------------------------------------------------
nav_pets, nav_schedule, nav_ai = st.tabs(["🐾 My Pets", "📅 Schedule", "AI Care Coach"])

# ===========================================================================
# PETS TAB
# ===========================================================================
with nav_pets:
    st.subheader("My Pets")

    pets = us.get_pets(user.id)

    if pets:
        pet_names = {p.name: p.id for p in pets}
        chosen_name = st.selectbox("Select a pet", list(pet_names.keys()), key="pet_selector")
        st.session_state.selected_pet_id = pet_names[chosen_name]
    else:
        st.info("No pets yet — add one below.")

    with st.expander("➕ Add New Pet"):
        np_name    = st.text_input("Pet name",        key="np_name")
        np_species = st.selectbox("Species", ["dog", "cat", "other"], key="np_species")
        np_breed   = st.text_input("Breed (optional)", key="np_breed")
        np_weight  = st.number_input("Weight (kg)",  min_value=0.0, step=0.1, key="np_weight")
        np_age     = st.number_input("Age (years)",  min_value=0,   step=1,   key="np_age")
        if st.button("Add Pet"):
            if not np_name:
                st.error("Pet name is required.")
            else:
                pet = ps_.create(
                    user_id=user.id,
                    name=np_name,
                    species=np_species,
                    breed=np_breed    or None,
                    weight_kg=np_weight if np_weight > 0 else None,
                    age_years=int(np_age) if np_age > 0 else None,
                )
                st.session_state.selected_pet_id = pet.id
                st.success(f"Added **{pet.name}**!")
                st.rerun()

    # ── Pet detail — only when a pet is selected ──────────────────────────
    if st.session_state.selected_pet_id:
        pet_id = st.session_state.selected_pet_id
        try:
            pet = ps_.get_profile(pet_id)
        except ValueError:
            st.session_state.selected_pet_id = None
            st.rerun()
            pet = None  # unreachable but keeps linter happy

        if pet:
            st.divider()
            st.subheader(f"🐾 {pet.name}")

            tab_profile, tab_targets, tab_activities, tab_score = st.tabs(
                ["Profile", "Care Targets", "Log Activity", "Care Score"]
            )

            # ── Profile ───────────────────────────────────────────────────
            with tab_profile:
                st.markdown(
                    f"**Species:** {pet.species} &nbsp;|&nbsp; "
                    f"**Breed:** {pet.breed or '—'} &nbsp;|&nbsp; "
                    f"**Weight:** {f'{pet.weight_kg} kg' if pet.weight_kg else '—'} &nbsp;|&nbsp; "
                    f"**Age:** {f'{pet.age_years} yr' if pet.age_years else '—'}"
                )

                with st.expander("Edit Profile"):
                    species_opts = ["dog", "cat", "other"]
                    upd_name    = st.text_input("Name",   value=pet.name,                                     key="upd_name")
                    upd_species = st.selectbox("Species", species_opts,
                                               index=species_opts.index(pet.species) if pet.species in species_opts else 2,
                                               key="upd_species")
                    upd_breed   = st.text_input("Breed",  value=pet.breed   or "",                            key="upd_breed")
                    upd_weight  = st.number_input("Weight (kg)",  min_value=0.0, step=0.1,
                                                  value=float(pet.weight_kg or 0.0),                         key="upd_weight")
                    upd_age     = st.number_input("Age (years)",  min_value=0,   step=1,
                                                  value=int(pet.age_years or 0),                             key="upd_age")
                    if st.button("Save Changes"):
                        ps_.update(
                            pet_id,
                            name=upd_name,
                            species=upd_species,
                            breed=upd_breed  or None,
                            weight_kg=upd_weight if upd_weight > 0 else None,
                            age_years=int(upd_age) if upd_age > 0 else None,
                        )
                        st.success("Profile updated!")
                        st.rerun()

                st.markdown("---")
                if st.button("🗑 Delete this pet", type="secondary"):
                    ps_.delete(pet_id)
                    st.session_state.selected_pet_id = None
                    st.success(f"{pet.name} deleted.")
                    st.rerun()

            # ── Care Targets ──────────────────────────────────────────────
            with tab_targets:
                try:
                    targets = cts.get_targets(pet_id)
                    st.markdown(
                        f"**Current targets** &nbsp;·&nbsp; Status: `{targets.status}`  \n"
                        f"Meals/day: **{targets.daily_meals}** &nbsp;|&nbsp; "
                        f"Walk: **{targets.daily_walk_min} min/day** &nbsp;|&nbsp; "
                        f"Grooming every **{targets.grooming_interval_days} days** &nbsp;|&nbsp; "
                        f"Vet every **{targets.vet_interval_days} days**"
                    )
                    if targets.status != "achieved":
                        if st.button("Mark as Achieved"):
                            cts.mark_achieved(pet_id)
                            st.success("Targets marked as achieved!")
                            st.rerun()
                except ValueError:
                    targets = None
                    st.info("No care targets set yet.")

                st.markdown("#### Set / Update Targets")
                tgt_meals = st.number_input("Daily meals",               min_value=1, step=1,
                                             value=targets.daily_meals               if targets else 2, key="tgt_meals")
                tgt_walk  = st.number_input("Daily walk (minutes)",      min_value=0, step=5,
                                             value=targets.daily_walk_min            if targets else 30, key="tgt_walk")
                tgt_groom = st.number_input("Grooming interval (days)",  min_value=1, step=1,
                                             value=targets.grooming_interval_days    if targets else 14, key="tgt_groom")
                tgt_vet   = st.number_input("Vet visit interval (days)", min_value=1, step=1,
                                             value=targets.vet_interval_days         if targets else 180, key="tgt_vet")
                if st.button("Save Targets"):
                    cts.set_targets(pet_id, int(tgt_meals), int(tgt_walk), int(tgt_groom), int(tgt_vet))
                    st.success("Care targets saved!")
                    st.rerun()

            # ── Log Activity ──────────────────────────────────────────────
            with tab_activities:
                st.markdown("#### Log an Activity")
                act_type = st.selectbox("Activity type",
                                        ["feeding", "walk", "grooming", "vet_visit"], key="act_type")
                act_date = st.date_input("Date", value=date.today(), key="act_date")

                details: dict = {}
                if act_type == "walk":
                    dur = st.number_input("Duration (minutes)", min_value=1, step=5, value=30, key="walk_dur")
                    details["duration_min"] = int(dur)
                elif act_type == "feeding":
                    notes = st.text_input("Food / notes (optional)", key="feed_notes")
                    if notes:
                        details["notes"] = notes
                elif act_type == "grooming":
                    notes = st.text_input("Groomer / notes (optional)", key="groom_notes")
                    if notes:
                        details["notes"] = notes
                elif act_type == "vet_visit":
                    notes = st.text_input("Reason / notes (optional)", key="vet_notes")
                    if notes:
                        details["notes"] = notes

                if st.button("Log Activity"):
                    acts.log_activity(pet_id, act_type, details, act_date)
                    st.success(f"{act_type.replace('_', ' ').title()} logged for {act_date}!")
                    st.rerun()

                st.markdown("#### Today's Activities")
                today_acts = acts.get_by_date(pet_id, date.today())
                if today_acts:
                    rows = [
                        {
                            "Type":    a.type.replace("_", " ").title(),
                            "Date":    str(a.date),
                            "Details": ", ".join(f"{k}: {v}" for k, v in a.details.items()) if a.details else "—",
                        }
                        for a in today_acts
                    ]
                    st.table(rows)
                else:
                    st.info("No activities logged today.")

            # ── Care Score ────────────────────────────────────────────────
            with tab_score:
                score_date = st.date_input("Score date", value=date.today(), key="score_date")
                if st.button("Calculate Score"):
                    try:
                        score = css.calculate(pet_id, score_date)
                        grade_colour = {"A": "green", "B": "blue", "C": "orange", "D": "red"}.get(score.grade, "grey")
                        st.markdown(
                            f"### Overall: **{score.overall_score}/100** &nbsp; "
                            f"<span style='color:{grade_colour};font-size:1.4rem'>Grade {score.grade}</span>",
                            unsafe_allow_html=True,
                        )
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Feeding",   f"{score.feeding_pct}%")
                        c2.metric("Exercise",  f"{score.exercise_pct}%")
                        c3.metric("Grooming",  f"{score.grooming_pct}%")
                        c4.metric("Vet",       f"{score.vet_pct}%")
                    except ValueError as e:
                        st.error(f"{e} — set care targets first.")

                st.markdown("#### Score History (last 30 days)")
                history = css.get_history(pet_id, 30)
                if history:
                    chart_data = {str(s.date): s.overall_score for s in history}
                    st.line_chart(chart_data)
                    rows = [
                        {
                            "Date":     str(s.date),
                            "Overall":  s.overall_score,
                            "Grade":    s.grade,
                            "Feeding":  f"{s.feeding_pct}%",
                            "Exercise": f"{s.exercise_pct}%",
                            "Grooming": f"{s.grooming_pct}%",
                            "Vet":      f"{s.vet_pct}%",
                        }
                        for s in reversed(history)
                    ]
                    st.dataframe(rows, use_container_width=True)
                else:
                    st.info("No score history yet. Calculate a score above to start tracking.")


# ===========================================================================
# SCHEDULE TAB
# ===========================================================================
with nav_schedule:
    st.subheader("Schedule")

    user_pets = us.get_pets(user.id)

    if not user_pets:
        st.info("Add pets in the **My Pets** tab first to start scheduling tasks.")
    else:
        pet_id_to_name = {p.id: p.name for p in user_pets}
        all_pet_ids    = [p.id for p in user_pets]

        sub_tasks, sub_targets = st.tabs(["Tasks", "Care Targets"])

        # ===================================================================
        # SUB-TAB: TASKS
        # ===================================================================
        with sub_tasks:
            # ── Filters ───────────────────────────────────────────────────
            col_search, col_pet, col_status, col_sort = st.columns([2, 2, 1, 2])

            with col_search:
                name_search = st.text_input(
                    "Search pet name",
                    key="task_name_search",
                    placeholder="e.g. Max",
                )

            with col_pet:
                filter_pets = st.multiselect(
                    "Filter by pet",
                    options=all_pet_ids,
                    default=all_pet_ids,
                    format_func=lambda pid: pet_id_to_name[pid],
                    key="sched_filter_pets",
                )

            with col_status:
                filter_status = st.selectbox(
                    "Status",
                    ["all", "pending", "done", "skipped"],
                    key="sched_filter_status",
                )

            with col_sort:
                sort_mode = st.selectbox(
                    "Sort by",
                    ["urgency", "care score", "completion gap"],
                    key="sched_sort_mode",
                )

            _SORT_DESCRIPTIONS = {
                "urgency":          "Overdue tasks surface first, then sorted by scheduled date.",
                "care score":       "Pets with the lowest overall care score are prioritised.",
                "completion gap":   "Pets furthest from meeting today's targets appear first.",
            }
            st.info(f"**Sort mode — {sort_mode.title()}:** {_SORT_DESCRIPTIONS[sort_mode]}")

            # Resolve active pet IDs: multiselect → name search refinement
            base_ids = filter_pets if filter_pets else all_pet_ids
            if name_search.strip():
                query = name_search.strip().lower()
                active_pet_ids = [
                    pid for pid in base_ids
                    if query in pet_id_to_name[pid].lower()
                ]
            else:
                active_pet_ids = base_ids

            status_filter = None if filter_status == "all" else filter_status

            # ── Build care-score / completion-gap maps ────────────────────
            score_map: dict[str, int]   = {}
            gap_map:   dict[str, float] = {}
            if sort_mode in ("care score", "completion gap"):
                for p in user_pets:
                    s = css.get_by_date(p.id, date.today())
                    if s:
                        score_map[p.id] = s.overall_score
                        feeding_gap  = max(0, 100 - s.feeding_pct)  / 100
                        exercise_gap = max(0, 100 - s.exercise_pct) / 100
                        gap_map[p.id] = (feeding_gap + exercise_gap) / 2

            # ── Fetch + sort ──────────────────────────────────────────────
            raw_tasks = ts.get_all_for_pets(active_pet_ids, status=status_filter)

            if sort_mode == "care score":
                tasks = ps.sort_by_care_score(raw_tasks, score_map)
            elif sort_mode == "completion gap":
                tasks = ps.sort_by_completion_gap(raw_tasks, gap_map)
            else:
                tasks = ps.sort_by_urgency(raw_tasks, date.today())

            # ── Conflict banner ───────────────────────────────────────────
            conflicts = ts.detect_conflicts(pet_ids=active_pet_ids, window_days=7)
            if conflicts:
                _conflict_cfg = {
                    "daily_overload":        ("🚨", "error",   "Daily Overload"),
                    "duplicate_non_feeding": ("⚠️", "warning", "Duplicate Task"),
                    "time_proximity":        ("🕐", "warning", "Time Overlap"),
                    "cross_pet_time_clash":  ("🐾", "warning", "Cross-Pet Clash"),
                }
                with st.expander(f"⚠️ {len(conflicts)} scheduling conflict(s) in the next 7 days", expanded=True):
                    for c in conflicts:
                        icon, level, label = _conflict_cfg.get(
                            c.conflict_type, ("ℹ️", "info", c.conflict_type)
                        )
                        msg = f"{icon} **{label}** — {c.message}"
                        if level == "error":
                            st.error(msg)
                        elif level == "warning":
                            st.warning(msg)
                        else:
                            st.info(msg)
            else:
                st.success("No scheduling conflicts in the next 7 days.")

            # ── Task list ─────────────────────────────────────────────────
            today = date.today()
            st.markdown(f"**{len(tasks)}** task(s) matching filters")

            if not tasks:
                st.info("No tasks found — schedule one below.")

            for task in tasks:
                days_diff = (task.scheduled_date - today).days
                if days_diff < 0:
                    urgency_badge = f"🔴 {abs(days_diff)}d overdue"
                    urgency_level = "overdue"
                elif days_diff == 0:
                    urgency_badge = "🟡 Due today"
                    urgency_level = "today"
                elif days_diff <= 3:
                    urgency_badge = f"🟢 In {days_diff}d"
                    urgency_level = "soon"
                else:
                    urgency_badge = f"⚪ In {days_diff}d"
                    urgency_level = "future"

                status_icon  = {"pending": "⏳", "done": "✅", "skipped": "⏭️"}.get(task.status, "")
                recur_labels = {"daily": "↻ Daily", "weekly": "↻ Weekly",
                                "custom": f"↻ Every {task.recurrence_interval_days}d"}
                recur_label  = recur_labels.get(task.recurrence, "")
                time_str     = f" @ {task.scheduled_time}" if task.scheduled_time else ""
                pet_name     = pet_id_to_name.get(task.pet_id, task.pet_id)

                with st.container(border=True):
                    col_info, col_actions = st.columns([4, 1])
                    with col_info:
                        header = (
                            f"{status_icon} **{task.task_type.replace('_', ' ').title()}** — "
                            f"{pet_name} · {task.scheduled_date}{time_str}"
                        )
                        if recur_label:
                            header += f" &nbsp; `{recur_label}`"
                        st.markdown(header)
                        if task.notes:
                            st.caption(f"📝 {task.notes}")
                        # Urgency callout
                        if urgency_level == "overdue":
                            st.error(urgency_badge)
                        elif urgency_level == "today":
                            st.warning(urgency_badge)
                        elif urgency_level == "soon":
                            st.info(urgency_badge)
                        else:
                            st.success(urgency_badge)

                    with col_actions:
                        if task.status == "pending":
                            c_done, c_skip = st.columns(2)
                            with c_done:
                                if st.button("✓", key=f"sched_done_{task.id}", help="Mark done"):
                                    next_task = ts.complete(task.id)
                                    msg = "✅ Marked done."
                                    if next_task:
                                        msg += f" Next: {next_task.scheduled_date}"
                                    st.success(msg)
                                    st.rerun()
                            with c_skip:
                                if st.button("⏭", key=f"sched_skip_{task.id}", help="Skip"):
                                    next_task = ts.skip(task.id)
                                    msg = "⏭️ Skipped."
                                    if next_task:
                                        msg += f" Next: {next_task.scheduled_date}"
                                    st.info(msg)
                                    st.rerun()

            # ── Add task form ─────────────────────────────────────────────
            with st.expander("➕ Schedule New Task"):
                form_pet = st.selectbox(
                    "Pet",
                    options=all_pet_ids,
                    format_func=lambda pid: pet_id_to_name[pid],
                    key="new_task_pet",
                )
                form_type = st.selectbox(
                    "Task type",
                    ["feeding", "walk", "grooming", "vet_visit"],
                    key="new_task_type",
                )
                form_date = st.date_input("Date", value=date.today(), key="new_task_date")
                form_time = st.text_input(
                    "Time (HH:MM, optional)", key="new_task_time", placeholder="e.g. 08:00"
                )
                form_recur = st.selectbox(
                    "Recurrence",
                    ["none", "daily", "weekly", "custom"],
                    key="new_task_recur",
                )
                form_interval = 0
                if form_recur == "custom":
                    form_interval = st.number_input(
                        "Repeat every N days", min_value=1, step=1, value=3, key="new_task_interval"
                    )
                form_notes = st.text_input("Notes (optional)", key="new_task_notes")

                if st.button("Add Task", key="sched_add_task"):
                    time_val = form_time.strip() or None
                    if time_val and not re.match(r"^\d{2}:\d{2}$", time_val):
                        st.error("Time must be in HH:MM format (e.g. 08:30).")
                    else:
                        ts.create(
                            pet_id=form_pet,
                            task_type=form_type,
                            scheduled_date=form_date,
                            scheduled_time=time_val,
                            recurrence=form_recur,
                            recurrence_interval_days=int(form_interval),
                            notes=form_notes.strip(),
                        )
                        st.success("Task scheduled!")
                        st.rerun()

        # ===================================================================
        # SUB-TAB: CARE TARGETS
        # ===================================================================
        with sub_targets:
            # ── Filters ───────────────────────────────────────────────────
            col_tgt_search, col_tgt_status = st.columns([2, 1])

            with col_tgt_search:
                tgt_name_search = st.text_input(
                    "Search pet name",
                    key="tgt_name_search",
                    placeholder="e.g. Luna",
                )

            with col_tgt_status:
                tgt_status_filter = st.selectbox(
                    "Status",
                    ["all", "pending", "achieved"],
                    key="tgt_status_filter",
                )

            # ── Build filtered targets table ──────────────────────────────
            rows = []
            for p in user_pets:
                # Pet name filter (case-insensitive substring)
                if tgt_name_search.strip() and tgt_name_search.strip().lower() not in p.name.lower():
                    continue

                try:
                    t = cts.get_targets(p.id)
                except ValueError:
                    # Pet has no targets — only show when status filter is "all"
                    if tgt_status_filter == "all":
                        rows.append({
                            "Pet":              p.name,
                            "Status":           "—",
                            "Meals / day":      "—",
                            "Walk (min/day)":   "—",
                            "Groom (days)":     "—",
                            "Vet (days)":       "—",
                        })
                    continue

                # Status filter
                if tgt_status_filter != "all" and t.status != tgt_status_filter:
                    continue

                rows.append({
                    "Pet":              p.name,
                    "Status":           t.status,
                    "Meals / day":      t.daily_meals,
                    "Walk (min/day)":   t.daily_walk_min,
                    "Groom (days)":     t.grooming_interval_days,
                    "Vet (days)":       t.vet_interval_days,
                })

            st.markdown(f"**{len(rows)}** target(s) matching filters")

            if rows:
                # Split into achieved vs pending for a summary header
                n_achieved = sum(1 for r in rows if r["Status"] == "achieved")
                n_pending  = sum(1 for r in rows if r["Status"] == "pending")
                if n_achieved:
                    st.success(f"✅ {n_achieved} pet(s) have met their care targets.")
                if n_pending:
                    st.warning(f"⏳ {n_pending} pet(s) still have pending targets.")

                # Render each target as a bordered card with status-appropriate callout
                for r in rows:
                    with st.container(border=True):
                        col_name, col_stats = st.columns([2, 5])
                        with col_name:
                            st.markdown(f"**{r['Pet']}**")
                            if r["Status"] == "achieved":
                                st.success("✅ Achieved")
                            elif r["Status"] == "pending":
                                st.warning("⏳ Pending")
                            else:
                                st.info("— No targets set")
                        with col_stats:
                            if r["Status"] != "—":
                                st.table({
                                    "Meals / day":    [r["Meals / day"]],
                                    "Walk (min/day)": [r["Walk (min/day)"]],
                                    "Groom (days)":   [r["Groom (days)"]],
                                    "Vet (days)":     [r["Vet (days)"]],
                                })
            else:
                st.info("No care targets match the current filters.")


# ===========================================================================
# AI CARE COACH TAB
# ===========================================================================
with nav_ai:
    st.subheader("AI Care Coach")
    st.caption(
        "Grounded planning assistant for routine pet care. It retrieves local care guidance, "
        "checks live app data, and only applies suggested tasks after you review them."
    )

    user_pets = us.get_pets(user.id)

    if not user_pets:
        st.info("Add pets in the **My Pets** tab first so the AI coach has context to work with.")
    else:
        pet_id_to_name = {pet.id: pet.name for pet in user_pets}
        all_pet_ids = [pet.id for pet in user_pets]
        default_pet_id = (
            st.session_state.selected_pet_id
            if st.session_state.selected_pet_id in all_pet_ids
            else all_pet_ids[0]
        )
        default_index = all_pet_ids.index(default_pet_id)

        ai_pet_id = st.selectbox(
            "Choose a pet",
            options=all_pet_ids,
            index=default_index,
            format_func=lambda pid: pet_id_to_name[pid],
            key="ai_pet_id",
        )
        ai_prompt = st.text_area(
            "What should the coach help with?",
            value=(
                "Explain what needs attention this week, summarize the biggest routine gaps, "
                "and suggest the next best care tasks."
            ),
            height=120,
            key="ai_prompt",
        )
        ai_horizon = st.slider(
            "Planning horizon (days)",
            min_value=3,
            max_value=14,
            value=7,
            key="ai_horizon",
        )

        if st.button("Generate AI care plan", key="ai_generate_plan"):
            try:
                st.session_state.last_ai_plan = ai_coach.generate_plan(
                    pet_id=ai_pet_id,
                    question=ai_prompt,
                    owner_pet_ids=all_pet_ids,
                    horizon_days=ai_horizon,
                )
                st.session_state.last_ai_plan_pet_id = ai_pet_id
                st.session_state.ai_last_apply_result = None
            except Exception as e:
                st.error(f"AI coach failed safely: {e}")

        plan = (
            st.session_state.last_ai_plan
            if st.session_state.last_ai_plan_pet_id == ai_pet_id
            else None
        )

        if plan:
            if plan.status == "emergency":
                st.error(plan.summary)
            else:
                st.success(plan.summary)

            metric_col, rationale_col = st.columns([1, 3])
            with metric_col:
                st.metric("Confidence", f"{int(plan.confidence * 100)}%")
            with rationale_col:
                st.info(plan.confidence_rationale)

            if plan.alerts:
                with st.expander("Safety and validation notes", expanded=True):
                    for alert in plan.alerts:
                        st.warning(alert)

            if plan.missing_data:
                with st.expander("Missing or weak context"):
                    for item in plan.missing_data:
                        st.info(item)

            st.markdown("### Findings")
            for finding in plan.findings:
                st.write(f"- {finding}")

            st.markdown("### Recommended actions")
            if plan.actions:
                for action in plan.actions:
                    due_text = action.due_date.isoformat() if action.due_date else "Review only"
                    task_mode = (
                        action.task_type.replace("_", " ").title()
                        if action.task_type
                        else "Guidance only"
                    )
                    with st.container(border=True):
                        st.markdown(f"**{action.title}**")
                        st.caption(
                            f"Priority: {action.priority.title()} | Due: {due_text} | Action type: {task_mode}"
                        )
                        st.write(action.rationale)
                        if action.evidence:
                            st.caption("Evidence: " + " | ".join(action.evidence))
                        if action.citations:
                            st.caption("Knowledge refs: " + ", ".join(action.citations))
            else:
                st.info("The coach did not generate any actions for this request.")

            suggested_tasks = [
                action for action in plan.actions if action.task_type and action.due_date
            ]
            if suggested_tasks and plan.status != "emergency":
                if st.button("Apply AI task suggestions", key="ai_apply_tasks"):
                    apply_result = ai_coach.apply_task_suggestions(plan)
                    st.session_state.ai_last_apply_result = apply_result
                    st.rerun()

            apply_result = st.session_state.ai_last_apply_result
            if apply_result:
                if apply_result.created_tasks:
                    st.success(
                        f"Added {len(apply_result.created_tasks)} AI-suggested task(s) to the schedule."
                    )
                for skipped_message in apply_result.skipped_messages:
                    st.info(skipped_message)

            st.markdown("### Retrieved knowledge")
            for item in plan.retrieved_knowledge:
                with st.expander(f"{item.title} ({item.doc_id})"):
                    st.caption(
                        f"Source: {item.source} | Match score: {item.score:.1f} | Matched terms: "
                        + (", ".join(item.matched_terms) if item.matched_terms else "general fallback")
                    )
                    st.write(item.excerpt)
        else:
            st.info(
                "Generate a plan to see an evidence-backed summary, confidence score, and optional task automation."
            )
