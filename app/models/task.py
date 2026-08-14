import uuid
import enum
from datetime import datetime, date
from sqlalchemy import String, Integer, DateTime, Date, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class TaskStatus(str, enum.Enum):
    new = "New"
    open = "Open"
    waiting_on_client = "Waiting on Client"
    waiting_on_vendor = "Waiting on Vendor"
    work_in_progress = "Work In Progress"
    closed_not_needed = "Closed - Not Needed"
    closed_complete = "Closed - Complete"


class TaskPriority(str, enum.Enum):
    low = "Low"
    medium = "Medium"
    high = "High"
    critical = "Critical"


# Valid state transitions
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.new: {
        TaskStatus.open,
        TaskStatus.work_in_progress,
        TaskStatus.waiting_on_client,
        TaskStatus.waiting_on_vendor,
        TaskStatus.closed_not_needed,
        TaskStatus.closed_complete,
    },
    TaskStatus.open: {
        TaskStatus.work_in_progress,
        TaskStatus.waiting_on_client,
        TaskStatus.waiting_on_vendor,
        TaskStatus.closed_not_needed,
        TaskStatus.closed_complete,
    },
    TaskStatus.work_in_progress: {
        TaskStatus.open,
        TaskStatus.waiting_on_client,
        TaskStatus.waiting_on_vendor,
        TaskStatus.closed_complete,
        TaskStatus.closed_not_needed,
    },
    TaskStatus.waiting_on_client: {
        TaskStatus.open,
        TaskStatus.work_in_progress,
        TaskStatus.waiting_on_vendor,
        TaskStatus.closed_not_needed,
        TaskStatus.closed_complete,
    },
    TaskStatus.waiting_on_vendor: {
        TaskStatus.open,
        TaskStatus.work_in_progress,
        TaskStatus.waiting_on_client,
        TaskStatus.closed_not_needed,
        TaskStatus.closed_complete,
    },
    TaskStatus.closed_complete: {
        TaskStatus.open,  # Reopen (Admin/Owner only)
        TaskStatus.work_in_progress,  # Reopen (Admin/Owner only)
    },
    TaskStatus.closed_not_needed: {
        TaskStatus.open,  # Reopen (Admin/Owner only)
        TaskStatus.work_in_progress,  # Reopen (Admin/Owner only)
    },
}


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("process_tabs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(5000), nullable=True, default="")
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False, default=TaskStatus.new,
    )
    percent_complete: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[TaskPriority | None] = mapped_column(
        Enum(TaskPriority, values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    tab = relationship("ProcessTab", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assigned_to], lazy="selectin")
    creator = relationship("User", foreign_keys=[created_by], lazy="selectin")
    notes = relationship("TaskNote", back_populates="task", lazy="selectin", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="task", lazy="selectin", cascade="all, delete-orphan")
