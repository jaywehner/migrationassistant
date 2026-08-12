import pytest
import uuid
from app.models.task import TaskStatus, VALID_TRANSITIONS, Task
from app.models.plan import PlanRole
from app.services.task_service import change_task_status


class TestStateTransitions:
    """Test the task status state machine rules."""

    def test_valid_transitions_defined_for_all_statuses(self):
        """Every status should have a set of valid transitions."""
        for status in TaskStatus:
            assert status in VALID_TRANSITIONS, f"Missing transitions for {status}"

    def test_new_can_go_to_open(self):
        assert TaskStatus.open in VALID_TRANSITIONS[TaskStatus.new]

    def test_new_can_go_to_wip(self):
        assert TaskStatus.work_in_progress in VALID_TRANSITIONS[TaskStatus.new]

    def test_new_can_go_to_closed_not_needed(self):
        assert TaskStatus.closed_not_needed in VALID_TRANSITIONS[TaskStatus.new]

    def test_new_cannot_go_to_closed_complete(self):
        assert TaskStatus.closed_complete not in VALID_TRANSITIONS[TaskStatus.new]

    def test_open_can_go_to_all_working_states(self):
        valid = VALID_TRANSITIONS[TaskStatus.open]
        assert TaskStatus.work_in_progress in valid
        assert TaskStatus.waiting_on_client in valid
        assert TaskStatus.waiting_on_vendor in valid
        assert TaskStatus.closed_complete in valid
        assert TaskStatus.closed_not_needed in valid

    def test_wip_can_go_to_waiting_states(self):
        valid = VALID_TRANSITIONS[TaskStatus.work_in_progress]
        assert TaskStatus.waiting_on_client in valid
        assert TaskStatus.waiting_on_vendor in valid

    def test_wip_can_close(self):
        valid = VALID_TRANSITIONS[TaskStatus.work_in_progress]
        assert TaskStatus.closed_complete in valid
        assert TaskStatus.closed_not_needed in valid

    def test_waiting_on_client_can_reopen(self):
        valid = VALID_TRANSITIONS[TaskStatus.waiting_on_client]
        assert TaskStatus.open in valid
        assert TaskStatus.work_in_progress in valid

    def test_waiting_on_vendor_can_reopen(self):
        valid = VALID_TRANSITIONS[TaskStatus.waiting_on_vendor]
        assert TaskStatus.open in valid
        assert TaskStatus.work_in_progress in valid

    def test_closed_complete_can_only_reopen(self):
        valid = VALID_TRANSITIONS[TaskStatus.closed_complete]
        assert valid == {TaskStatus.open}

    def test_closed_not_needed_can_only_reopen(self):
        valid = VALID_TRANSITIONS[TaskStatus.closed_not_needed]
        assert valid == {TaskStatus.open}

    def test_no_self_transitions_in_closed(self):
        assert TaskStatus.closed_complete not in VALID_TRANSITIONS[TaskStatus.closed_complete]
        assert TaskStatus.closed_not_needed not in VALID_TRANSITIONS[TaskStatus.closed_not_needed]


class TestChangeTaskStatus:
    """Test the change_task_status service function."""

    @pytest.mark.asyncio
    async def test_valid_transition(self, db_session):
        task = Task(
            id=uuid.uuid4(),
            tab_id=uuid.uuid4(),
            title="Test",
            status=TaskStatus.new,
            created_by=uuid.uuid4(),
        )
        plan_id = uuid.uuid4()

        success, error = await change_task_status(
            db_session, task, TaskStatus.open,
            uuid.uuid4(), plan_id, PlanRole.admin,
        )
        assert success is True
        assert error == ""
        assert task.status == TaskStatus.open

    @pytest.mark.asyncio
    async def test_invalid_transition(self, db_session):
        task = Task(
            id=uuid.uuid4(),
            tab_id=uuid.uuid4(),
            title="Test",
            status=TaskStatus.new,
            created_by=uuid.uuid4(),
        )
        plan_id = uuid.uuid4()

        success, error = await change_task_status(
            db_session, task, TaskStatus.closed_complete,
            uuid.uuid4(), plan_id, PlanRole.admin,
        )
        assert success is False
        assert "Cannot transition" in error

    @pytest.mark.asyncio
    async def test_reopen_requires_admin(self, db_session):
        task = Task(
            id=uuid.uuid4(),
            tab_id=uuid.uuid4(),
            title="Test",
            status=TaskStatus.closed_complete,
            created_by=uuid.uuid4(),
        )
        plan_id = uuid.uuid4()

        # Contributor cannot reopen
        success, error = await change_task_status(
            db_session, task, TaskStatus.open,
            uuid.uuid4(), plan_id, PlanRole.contributor,
        )
        assert success is False
        assert "Admin or Owner" in error

        # Admin can reopen
        success, error = await change_task_status(
            db_session, task, TaskStatus.open,
            uuid.uuid4(), plan_id, PlanRole.admin,
        )
        assert success is True

    @pytest.mark.asyncio
    async def test_closing_complete_sets_100_percent(self, db_session):
        task = Task(
            id=uuid.uuid4(),
            tab_id=uuid.uuid4(),
            title="Test",
            status=TaskStatus.open,
            percent_complete=50,
            created_by=uuid.uuid4(),
        )
        plan_id = uuid.uuid4()

        await change_task_status(
            db_session, task, TaskStatus.closed_complete,
            uuid.uuid4(), plan_id, PlanRole.admin,
        )
        assert task.percent_complete == 100

    @pytest.mark.asyncio
    async def test_closing_not_needed_sets_0_percent(self, db_session):
        task = Task(
            id=uuid.uuid4(),
            tab_id=uuid.uuid4(),
            title="Test",
            status=TaskStatus.open,
            percent_complete=50,
            created_by=uuid.uuid4(),
        )
        plan_id = uuid.uuid4()

        await change_task_status(
            db_session, task, TaskStatus.closed_not_needed,
            uuid.uuid4(), plan_id, PlanRole.admin,
        )
        assert task.percent_complete == 0
