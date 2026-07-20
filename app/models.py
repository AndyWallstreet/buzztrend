"""SQLAlchemy ORM models."""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    term = Column(String, unique=True, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    counts = relationship("BuzzDaily", back_populates="keyword",
                          cascade="all, delete-orphan")


class BuzzDaily(Base):
    """One row = buzz count for (keyword, channel, day)."""
    __tablename__ = "buzz_daily"
    __table_args__ = (
        UniqueConstraint("keyword_id", "channel", "date", name="uq_buzz_daily"),
    )

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=False, index=True)
    channel = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    count = Column(Integer, default=0, nullable=False)

    keyword = relationship("Keyword", back_populates="counts")


class BuzzSnapshot(Base):
    """Raw all-time totals from APIs that can't filter by date (Naver).

    The daily count is derived as the delta between consecutive snapshots.
    """
    __tablename__ = "buzz_snapshots"
    __table_args__ = (
        UniqueConstraint("keyword_id", "channel", "date",
                         name="uq_buzz_snapshot"),
    )

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=False, index=True)
    channel = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    total = Column(Integer, nullable=False)


class AlertEvent(Base):
    """A recorded spike detection."""
    __tablename__ = "alert_events"
    __table_args__ = (
        UniqueConstraint("keyword_id", "channel", "date", name="uq_alert_event"),
    )

    id = Column(Integer, primary_key=True)
    keyword_id = Column(Integer, ForeignKey("keywords.id"), nullable=False, index=True)
    channel = Column(String, nullable=False)
    date = Column(Date, nullable=False)
    count = Column(Integer, nullable=False)
    baseline = Column(Float, nullable=False)
    ratio = Column(Float, nullable=False)
    message = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    keyword = relationship("Keyword")
