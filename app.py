import streamlit as st
from datetime import datetime
from pawpal_system import Owner, Pet, Task, Scheduler
from main import initialize_demo
from ai_care_assistant import generate_care_plan


# Page configuration
st.set_page_config(page_title="PawPal", layout="wide")
st.title("🐾 PawPal - Pet Care Task Manager")

# Initialize session state for persistence across reruns
if "owner" not in st.session_state or "scheduler" not in st.session_state:
    st.session_state.owner, st.session_state.scheduler = initialize_demo()


def initialize_owner(owner_name: str, contact_info: str):
    """Initialize owner and scheduler in session state."""
    st.session_state.owner = Owner(ownerId="1", name=owner_name, contactInfo=contact_info)
    st.session_state.scheduler = Scheduler(owner=st.session_state.owner)
    st.session_state.owner.scheduler = st.session_state.scheduler


# Sidebar for owner setup
with st.sidebar:
    st.header("Owner Setup")

    if st.session_state.owner is None:
        owner_name = st.text_input("Owner Name", placeholder="Enter your name")
        contact_info = st.text_input("Contact Info", placeholder="Enter email or phone")

        if st.button("Initialize PawPal"):
            if owner_name and contact_info:
                initialize_owner(owner_name, contact_info)
                st.success(f"Welcome, {owner_name}!")
            else:
                st.error("Please fill in all fields")
    else:
        st.write(f"**Owner:** {st.session_state.owner.name}")
        st.write(f"**Contact:** {st.session_state.owner.contactInfo}")
        st.write(f"**Pets:** {len(st.session_state.owner.pets)}")


# Main app content
if st.session_state.owner is None:
    st.info("👈 Please set up your owner profile in the sidebar to get started!")
else:
    # Navigation tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📅 Today's Schedule", "🐕 Manage Pets", "📝 Add Task", "⚙️ Manage Tasks", "🤖 AI Care Assistant"
    ])

    # Tab 1: Today's Schedule
    with tab1:
        st.header("Today's Schedule")
        if len(st.session_state.scheduler.tasks) == 0:
            st.info("No tasks scheduled yet. Add a pet and task to get started!")
        else:
            # Display conflict warnings if any
            conflicts = st.session_state.scheduler.detectConflicts()
            if conflicts:
                with st.expander("⚠️ Scheduling Conflicts Detected", expanded=True):
                    for conflict in conflicts:
                        st.warning(conflict)
            else:
                st.success("✓ No scheduling conflicts detected!")

            st.divider()
            st.subheader("Schedule")
            st.session_state.scheduler.viewSchedule(display_func=st.write, show_header=False)

    # Tab 2: Manage Pets
    with tab2:
        st.header("Manage Pets")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Add New Pet")
            pet_name = st.text_input("Pet Name", key="pet_name_input")
            pet_type = st.selectbox("Pet Type", ["dog", "cat", "bird", "other"], key="pet_type_select")
            pet_breed = st.text_input("Breed", key="pet_breed_input")
            pet_age = st.number_input("Age", min_value=0, max_value=50, key="pet_age_input")
            pet_health = st.text_area("Health Info", key="pet_health_input", height=80)
            pet_activity = st.selectbox("Activity Level", ["low", "medium", "high"], key="pet_activity_select")

            if st.button("Add Pet", key="add_pet_btn"):
                if pet_name and pet_breed:
                    new_pet = Pet(
                        petId=str(len(st.session_state.owner.pets) + 1),
                        name=pet_name,
                        type=pet_type,
                        breed=pet_breed,
                        age=pet_age,
                        healthInfo=pet_health,
                        activityLevel=pet_activity,
                        scheduler=st.session_state.scheduler
                    )
                    st.session_state.owner.addPet(new_pet)
                    st.success(f"✓ {pet_name} added successfully!")
                    st.rerun()
                else:
                    st.error("Please fill in required fields (Name and Breed)")

        with col2:
            st.subheader("Your Pets")
            if len(st.session_state.owner.pets) == 0:
                st.info("No pets yet. Add your first pet!")
            else:
                for pet in st.session_state.owner.pets:
                    with st.expander(f"🐾 {pet.name} ({pet.breed})"):
                        st.write(pet.getDetails())
                        st.write(f"**Tasks:** {len(pet.getTasks())}")
                        if st.button(f"Remove {pet.name}", key=f"remove_{pet.petId}"):
                            st.session_state.owner.removePet(pet.petId)
                            st.success(f"{pet.name} removed")
                            st.rerun()

    # Tab 3: Add Task
    with tab3:
        st.header("Add New Task")

        if len(st.session_state.owner.pets) == 0:
            st.warning("Please add a pet first!")
        else:
            pet_options = {pet.name: pet.petId for pet in st.session_state.owner.pets}
            selected_pet_name = st.selectbox("Select Pet", list(pet_options.keys()), key="selected_pet_select")
            selected_pet_id = pet_options[selected_pet_name]

            with st.form("add_task_form"):
                task_description = st.text_input("Task Description", placeholder="e.g., Morning walk", key="task_description_input")
                task_time = st.time_input("Task Time", value=datetime.now().time(), key="task_time_input")
                task_frequency = st.selectbox("Frequency", ["one-time", "daily", "weekly", "monthly", "yearly"], key="task_frequency_select")
                task_priority = st.selectbox("Priority", ["low", "medium", "high"], key="task_priority_select")
                task_duration = st.number_input("Duration (minutes)", min_value=1, value=30, key="task_duration_input")

                if st.form_submit_button("Add Task"):
                    if task_description:
                        task_datetime = datetime.now().replace(
                            hour=task_time.hour,
                            minute=task_time.minute,
                            second=0,
                            microsecond=0
                        )
                        new_task = Task(
                            taskId=str(len(st.session_state.scheduler.tasks) + 1),
                            petId=selected_pet_id,
                            description=task_description,
                            time=task_datetime,
                            frequency=task_frequency,
                            priority=task_priority,
                            duration=task_duration,
                            completionStatus="pending"
                        )
                        st.session_state.owner.addTask(new_task)
                        st.success(f"✓ Task added for {selected_pet_name}!")
                        st.rerun()
                    else:
                        st.error("Please enter a task description")

    # Tab 4: Manage Tasks
    with tab4:
        st.header("Manage Tasks")

        if len(st.session_state.scheduler.tasks) == 0:
            st.info("No tasks yet. Create a task to get started!")
        else:
            # Filter controls
            col1, col2 = st.columns(2)

            with col1:
                filter_status = st.selectbox(
                    "Filter by Status",
                    ["All", "pending", "completed", "missed"],
                    key="filter_status"
                )

            with col2:
                pet_options = ["All"] + [pet.name for pet in st.session_state.owner.pets]
                filter_pet = st.selectbox(
                    "Filter by Pet",
                    pet_options,
                    key="filter_pet"
                )

            # Apply filters
            filtered_tasks = st.session_state.scheduler.tasks

            if filter_status != "All":
                filtered_tasks = st.session_state.scheduler.getTasksByStatus(filter_status)

            if filter_pet != "All":
                pet_filtered = st.session_state.scheduler.getTasksByPetName(filter_pet)
                if filter_status != "All":
                    filtered_tasks = [t for t in pet_filtered if t.completionStatus == filter_status]
                else:
                    filtered_tasks = pet_filtered

            st.divider()
            st.caption(f"Showing {len(filtered_tasks)} of {len(st.session_state.scheduler.tasks)} tasks")

            for task in filtered_tasks:
                pet = next((p for p in st.session_state.owner.pets if p.petId == task.petId), None)
                pet_name = pet.name if pet else "Unknown"

                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.write(f"**{pet_name}** - {task.description} ({task.time.strftime('%H:%M')})")
                    st.caption(f"Priority: {task.priority} | Duration: {task.duration} min | Status: {task.completionStatus}")

                with col2:
                    if task.completionStatus == "pending":
                        if st.button("✓ Complete", key=f"complete_{task.taskId}"):
                            st.session_state.scheduler.taskCompleted(task.taskId)
                            st.success("Task marked complete!")
                            st.rerun()

                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{task.taskId}"):
                        st.session_state.scheduler.removeTask(task.taskId)
                        st.success("Task deleted!")
                        st.rerun()

    # Tab 5: AI Care Assistant
    with tab5:
        st.header("AI Care Assistant")
        st.caption(
            "Retrieves breed/age/activity-matched care guidelines, drafts a set of "
            "tasks grounded in them, and self-checks the draft against your existing "
            "schedule before showing it to you."
        )

        if "ai_care_plan_results" not in st.session_state:
            st.session_state.ai_care_plan_results = {}

        if len(st.session_state.owner.pets) == 0:
            st.warning("Please add a pet first!")
        else:
            pet_options = {pet.name: pet.petId for pet in st.session_state.owner.pets}
            selected_pet_name = st.selectbox("Select Pet", list(pet_options.keys()), key="ai_pet_select")
            selected_pet_id = pet_options[selected_pet_name]
            selected_pet = next(p for p in st.session_state.owner.pets if p.petId == selected_pet_id)

            if st.button("Generate AI Care Plan", key="generate_ai_plan_btn"):
                with st.spinner(f"Consulting Gemini for a care plan for {selected_pet_name}..."):
                    result = generate_care_plan(selected_pet, st.session_state.scheduler)
                st.session_state.ai_care_plan_results[selected_pet_id] = result

            result = st.session_state.ai_care_plan_results.get(selected_pet_id)

            if result is not None:
                st.divider()

                if result.error:
                    st.error(result.error)
                    if "GEMINI_API_KEY" in result.error:
                        st.info("Copy `.env.example` to `.env` and add your Gemini API key.")
                else:
                    st.success(
                        f"Proposed {len(result.tasks)} task(s) using {len(result.guideline_ids_used)} "
                        f"guideline(s) over {result.iterations_used} iteration(s)."
                    )

                    if result.guideline_ids_used:
                        with st.expander("Guidelines used"):
                            for gid in result.guideline_ids_used:
                                st.write(f"- {gid}")

                    for task in result.tasks:
                        st.write(f"**{task.time.strftime('%H:%M')}** — {task.description} "
                                 f"({task.duration} min, {task.frequency}, {task.priority} priority)")

                    if result.remaining_conflicts:
                        with st.expander("⚠️ Unresolved conflicts", expanded=True):
                            for conflict in result.remaining_conflicts:
                                st.warning(conflict)

                    if result.tasks:
                        if st.button("Add All to Schedule", key="add_ai_tasks_btn"):
                            for task in result.tasks:
                                st.session_state.owner.addTask(task)
                            del st.session_state.ai_care_plan_results[selected_pet_id]
                            st.success(f"Added {len(result.tasks)} task(s) to {selected_pet_name}'s schedule!")
                            st.rerun()
