import pytest
import uuid
from app.models.plan import PlanRole
from app.models.task import Task, TaskStatus
from app.services.plan_service import (
    can_manage_members,
    can_edit_plan,
    can_create_tasks,
    can_view_plan,
)
from app.services.task_service import can_edit_task


class TestPlanPermissions:
    def test_owner_can_manage_members(self):
        assert can_manage_members(PlanRole.owner) is True

    def test_admin_can_manage_members(self):
        assert can_manage_members(PlanRole.admin) is True

    def test_contributor_cannot_manage_members(self):
        assert can_manage_members(PlanRole.contributor) is False

    def test_viewer_cannot_manage_members(self):
        assert can_manage_members(PlanRole.viewer) is False

    def test_owner_can_edit_plan(self):
        assert can_edit_plan(PlanRole.owner) is True

    def test_admin_can_edit_plan(self):
        assert can_edit_plan(PlanRole.admin) is True

    def test_contributor_cannot_edit_plan(self):
        assert can_edit_plan(PlanRole.contributor) is False

    def test_viewer_cannot_edit_plan(self):
        assert can_edit_plan(PlanRole.viewer) is False

    def test_owner_can_create_tasks(self):
        assert can_create_tasks(PlanRole.owner) is True

    def test_admin_can_create_tasks(self):
        assert can_create_tasks(PlanRole.admin) is True

    def test_contributor_can_create_tasks(self):
        assert can_create_tasks(PlanRole.contributor) is True

    def test_viewer_cannot_create_tasks(self):
        assert can_create_tasks(PlanRole.viewer) is False

    def test_any_role_can_view_plan(self):
        for role in PlanRole:
            assert can_view_plan(role) is True


class TestTaskPermissions:
    def _make_task(self, assigned_to=None):
        return Task(
            id=uuid.uuid4(),
            tab_id=uuid.uuid4(),
            title="Test Task",
            status=TaskStatus.new,
            created_by=uuid.uuid4(),
            assigned_to=assigned_to,
        )

    def test_owner_can_edit_any_task(self):
        task = self._make_task()
        assert can_edit_task(PlanRole.owner, task, uuid.uuid4()) is True

    def test_admin_can_edit_any_task(self):
        task = self._make_task()
        assert can_edit_task(PlanRole.admin, task, uuid.uuid4()) is True

    def test_contributor_can_edit_assigned_task(self):
        user_id = uuid.uuid4()
        task = self._make_task(assigned_to=user_id)
        assert can_edit_task(PlanRole.contributor, task, user_id) is True

    def test_contributor_cannot_edit_unassigned_task(self):
        task = self._make_task()
        assert can_edit_task(PlanRole.contributor, task, uuid.uuid4()) is False

    def test_contributor_cannot_edit_other_user_task(self):
        task = self._make_task(assigned_to=uuid.uuid4())
        assert can_edit_task(PlanRole.contributor, task, uuid.uuid4()) is False

    def test_viewer_cannot_edit_any_task(self):
        task = self._make_task()
        assert can_edit_task(PlanRole.viewer, task, uuid.uuid4()) is False
