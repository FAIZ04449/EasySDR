from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class ICPConfig(Base):
    __tablename__ = "icp_configs"

    id = Column(Integer, primary_key=True, index=True)
    industry = Column(String, default="insurance")
    sub_vertical = Column(String, default="MGA")
    geography = Column(String, default="USA")
    min_employee = Column(Integer, default=50)
    max_employee = Column(Integer, default=5000)
    keywords = Column(Text, nullable=True)          # Comma-separated keywords
    excluded_keywords = Column(Text, nullable=True) # Comma-separated exclusions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    domain = Column(String, unique=True, index=True)
    industry = Column(String, nullable=True)
    employee_count = Column(Integer, nullable=True)
    revenue = Column(String, nullable=True)
    ai_score = Column(Integer, nullable=True)       # Fit score 0-100
    ai_explanation = Column(Text, nullable=True)    # LLM summary of why it's a fit
    discovery_source = Column(String, default="Apollo")
    status = Column(String, default="discovered")   # discovered, qualified, disqualified, synced
    hubspot_id = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String, index=True)
    title = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    confidence_score = Column(Integer, default=0)
    status = Column(String, default="discovered")   # discovered, enriched, validated, synced, ignored
    hubspot_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("Company", back_populates="contacts")

class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String)  # "company" or "contact"
    entity_id = Column(Integer)
    hubspot_id = Column(String, nullable=True)
    status = Column(String)       # "success" or "failed"
    error_message = Column(Text, nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow)

class ScrapingSession(Base):
    __tablename__ = "scraping_sessions"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default="linkedin")
    status = Column(String, default="running")  # running, success, failed
    logs = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)

class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String)  # "contact_title", "company_name", "company_domain"
    value = Column(String, index=True)
    feedback_type = Column(String, default="manual_push") # "manual_push", "score_override"
    created_at = Column(DateTime, default=datetime.utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=True)


