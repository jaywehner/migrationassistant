import uuid
import enum
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class PlanRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    contributor = "contributor"
    viewer = "viewer"


class MigrationPlan(Base):
    __tablename__ = "migration_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=True, default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", back_populates="owned_plans", lazy="selectin")
    members = relationship("PlanMember", back_populates="plan", lazy="selectin", cascade="all, delete-orphan")
    tabs = relationship("ProcessTab", back_populates="plan", lazy="selectin", cascade="all, delete-orphan")
    invites = relationship("PlanInvite", back_populates="plan", lazy="selectin", cascade="all, delete-orphan")


class PlanMember(Base):
    __tablename__ = "plan_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_plans.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[PlanRole] = mapped_column(Enum(PlanRole), nullable=False, default=PlanRole.contributor)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    plan = relationship("MigrationPlan", back_populates="members")
    user = relationship("User", back_populates="plan_memberships", foreign_keys=[user_id])


class PlanInvite(Base):
    __tablename__ = "plan_invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("migration_plans.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    role: Mapped[PlanRole] = mapped_column(Enum(PlanRole), nullable=False, default=PlanRole.contributor)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    plan = relationship("MigrationPlan", back_populates="invites")
