"""
SQL models.

Facility: clinics, hospitals, evacuation centers — the map data.
StatusUpdate: one capacity/availability report for a facility. Rows are never
    edited or deleted, so they form the history; the newest row is the status.
CachedResponse: generic key/value cache for AI outputs (prep plans, weather
    explainers, etc.) so the frontend can fetch-once and reuse offline.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func

from .database import Base


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True, index=True)
    # Stable identity from the data file (see main.sync_facilities). The numeric
    # id above is kept across restarts by matching rows on this key.
    key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # "hospital" | "clinic" | "evacuation_center"
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String, nullable=True)
    contact = Column(String, nullable=True)
    notes = Column(Text, nullable=True)


class UserEvacuationCenter(Base):
    """
    An evacuation center added through the API. Each row also has a matching
    `facilities` row (key "user:<id>"), so map, status history and ids work the
    same as for OSM and manual centers. Rows are never deleted: removing a center
    is recorded in FacilityRemoval.
    """
    __tablename__ = "user_evacuation_centers"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    center_type = Column(String, nullable=False)  # "permanent" | "temporary"
    barangay = Column(String, nullable=True)
    address = Column(String, nullable=True)
    contact = Column(String, nullable=True)
    max_capacity = Column(Integer, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    note = Column(String(140), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class FacilityRemoval(Base):
    """
    Soft delete. A center is hidden while it has a row here with restored_at
    empty. Keyed by the facility `key` (not the numeric id) so it works for
    OSM / manual / user centers and survives a rebuild of the facilities table.
    Restoring sets restored_at; rows are kept as history.
    """
    __tablename__ = "facility_removals"

    id = Column(Integer, primary_key=True)
    facility_key = Column(String, nullable=False, index=True)
    removed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    restored_at = Column(DateTime, nullable=True)


class ActionLog(Base):
    """Who-did-what trail for add / remove / restore. The IP is stored hashed only."""
    __tablename__ = "action_log"

    id = Column(Integer, primary_key=True)
    action = Column(String, nullable=False)  # "add" | "remove" | "restore"
    facility_key = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    ip_hash = Column(String, nullable=False)


class StatusUpdate(Base):
    """Capacity / availability report. Newest row per facility = current status."""
    __tablename__ = "status_updates"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id"), nullable=False)
    status = Column(String, nullable=False)  # open | almost_full | busy | full | closed
    people_inside = Column(Integer, nullable=True)
    max_capacity = Column(Integer, nullable=True)
    resources = Column(Text, nullable=True)  # JSON list, e.g. '["food","water"]'
    note = Column(String(140), nullable=True)
    # Always UTC. SQLite does not keep time zones, so reads come back naive and
    # status_service treats them as UTC.
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    __table_args__ = (Index("ix_status_updates_facility_id_id", "facility_id", "id"),)


class CachedResponse(Base):
    """
    Generic cache row for AI-generated content.
    `key` examples: "prep_plan:household_hash", "weather_explainer:2026-09-29"
    Frontend stores the same thing in IndexedDB for offline use; this table
    is the server-side source of truth / fallback.
    """
    __tablename__ = "cached_responses"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    kind = Column(String, nullable=False)  # "prep_plan" | "weather_explainer" | "report_draft" | "hazard_assessment"
    content = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime(timezone=True), server_default=func.now())
