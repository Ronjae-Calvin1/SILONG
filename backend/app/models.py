"""
SQL models.

Facility: clinics, hospitals, evacuation centers — the map data.
StatusUpdate: one capacity/availability report for a facility. Rows are never
    edited or deleted, so they form the history; the newest row is the status.
User / AuthSession / AuditLog: staff accounts (Responder, Super admin), their
    sign-in sessions, and the trail of admin actions (see accounts.py, audit.py).
Report / BlockedPhone: help requests and hazard reports from the public, and
    the phones blocked after too many false reports (see report_service.py).
CachedResponse: generic key/value cache for AI outputs (prep plans, weather
    explainers, etc.) so the frontend can fetch-once and reuse offline.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
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


class User(Base):
    """
    A staff account. The public has no account. Passwords are stored hashed
    only (see security.py). Times are naive UTC, like the other tables.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)  # as typed, shown in screens and the audit log
    name_key = Column(String, unique=True, index=True, nullable=False)  # lower case, one space between words: sign-in key
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "responder" | "super_admin"
    failed_attempts = Column(Integer, nullable=False, default=0)  # wrong passwords in a row
    locked_until = Column(DateTime, nullable=True)  # automatic lock after too many wrong tries
    is_locked = Column(Boolean, nullable=False, default=False)  # lock set by a Super admin, stays until unlocked
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    created_by = Column(String, nullable=True)  # name of the creator, kept as text
    last_sign_in_at = Column(DateTime, nullable=True)


class AuthSession(Base):
    """
    One signed-in browser. The token itself is never stored, only its hash.
    last_used_at moves forward on every request; a session idle for longer than
    STAFF_IDLE_MINUTES is dead.
    """
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_used_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class AuditLog(Base):
    """
    Every admin action, with the person's name. Rows are never edited or
    deleted. The name and role are copied in as text, so the entry still reads
    correctly after an account is removed. The IP is stored hashed only.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    actor_id = Column(Integer, nullable=True)  # no foreign key on purpose: accounts can be removed
    actor_name = Column(String, nullable=False)
    actor_role = Column(String, nullable=True)
    action = Column(String, nullable=False, index=True)  # e.g. "user.create", "auth.sign_in"
    target = Column(String, nullable=True)  # what it was done to, e.g. "user:3 (Ana)"
    detail = Column(Text, nullable=True)  # JSON text with the specifics
    ip_hash = Column(String, nullable=True)


class Report(Base):
    """
    One report from a phone: kind "help" (I need help) or "hazard". No photo and
    no name. Exact location and contact are for responders only. The phone ID
    and the IP are stored hashed only. Times are naive UTC.

    Hazard reports about the same place share a group_id (the id of the first
    one); a help request has no group. group_id is a plain number, not a
    foreign key, so purging old rows never breaks a group.
    """
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False)  # "help" | "hazard"
    status = Column(String, nullable=False, default="new")  # new | being_handled | resolved | false
    phone_hash = Column(String, nullable=False, index=True)
    ip_hash = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    contact = Column(String, nullable=True)
    note = Column(String(140), nullable=True)
    # Added in part 2b. Empty on reports sent before that (see report_service.upgrade_report_columns).
    category = Column(String(40), nullable=True)  # what the hazard or need is, e.g. "Flooded road"
    people = Column(Integer, nullable=True)  # help requests only: how many people need help
    can_move = Column(String, nullable=True)  # help requests only: "yes" | "no" | "unsure"
    group_id = Column(Integer, nullable=True, index=True)  # hazards only
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    taken_by = Column(String, nullable=True)  # staff name as text (accounts can be removed)
    taken_at = Column(DateTime, nullable=True)
    closed_by = Column(String, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)  # what was done (required to resolve)
    false_reason = Column(Text, nullable=True)  # why it is false (required to mark false)
    verified_by = Column(String, nullable=True)
    verified_at = Column(DateTime, nullable=True)

    __table_args__ = (Index("ix_reports_kind_status", "kind", "status"),)


class BlockedPhone(Base):
    """A phone (hashed ID) that may no longer send reports. Kept when old reports are purged."""
    __tablename__ = "blocked_phones"

    id = Column(Integer, primary_key=True)
    phone_hash = Column(String, unique=True, index=True, nullable=False)
    blocked_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    false_reports = Column(Integer, nullable=False, default=0)  # how many it had when blocked


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
