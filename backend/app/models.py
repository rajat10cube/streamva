"""SQLAlchemy models — baseline schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    all_libraries: Mapped[bool] = mapped_column(Boolean, default=True)  # access to every library
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Library(Base):
    __tablename__ = "library"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String, unique=True)
    group_depth: Mapped[int] = mapped_column(Integer, default=-1)  # -1 = auto-detect
    name: Mapped[str | None] = mapped_column(String, nullable=True)


class LibraryAccess(Base):
    """Explicit per-user library grants (used when a user's all_libraries is off)."""

    __tablename__ = "library_access"
    __table_args__ = (UniqueConstraint("user_id", "library_id", name="uq_library_access"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("library.id", ondelete="CASCADE"), index=True)


class Course(Base):
    __tablename__ = "course"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    library_id: Mapped[int | None] = mapped_column(
        ForeignKey("library.id", ondelete="CASCADE"), nullable=True
    )
    path: Mapped[str] = mapped_column(String, unique=True)
    cover_path: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    lecture_count: Mapped[int] = mapped_column(Integer, default=0)
    total_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sections: Mapped[list["Section"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Section(Base):
    __tablename__ = "section"
    __table_args__ = (UniqueConstraint("course_id", "path", name="uq_section_course_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    position: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="sections")
    lectures: Mapped[list["Lecture"]] = relationship(
        back_populates="section", cascade="all, delete-orphan"
    )


class Lecture(Base):
    __tablename__ = "lecture"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("section.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)  # video|audio|document
    mime: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    needs_transcode: Mapped[bool] = mapped_column(Boolean, default=False)
    video_codec: Mapped[str | None] = mapped_column(String, nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    subtitle_path: Mapped[str | None] = mapped_column(String, nullable=True)

    section: Mapped["Section"] = relationship(back_populates="lectures")


class Attachment(Base):
    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("section.id", ondelete="CASCADE"), nullable=True
    )
    lecture_id: Mapped[int | None] = mapped_column(
        ForeignKey("lecture.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String, default="resource")  # resource|bundle|link
    mime: Mapped[str | None] = mapped_column(String, nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)


class Note(Base):
    __tablename__ = "note"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lecture.id", ondelete="CASCADE"), index=True)
    position_sec: Mapped[float] = mapped_column(Float, default=0.0)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lecture_id", name="uq_progress_user_lecture"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lecture.id", ondelete="CASCADE"))
    position_sec: Mapped[float] = mapped_column(Float, default=0.0)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
