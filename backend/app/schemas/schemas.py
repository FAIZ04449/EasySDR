from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

# --- ICP Config Schemas ---
class ICPConfigBase(BaseModel):
    industry: str
    sub_vertical: str
    geography: str
    min_employee: int
    max_employee: int
    keywords: Optional[str] = None
    excluded_keywords: Optional[str] = None
    is_active: bool = True

class ICPConfigCreate(ICPConfigBase):
    pass

class ICPConfigResponse(ICPConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Contact Schemas ---
class ContactBase(BaseModel):
    name: str
    title: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    confidence_score: int = 0
    status: str = "discovered"
    hubspot_id: Optional[str] = None

class ContactCreate(ContactBase):
    company_id: int

class ContactResponse(ContactBase):
    id: int
    company_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Company Schemas ---
class CompanyBase(BaseModel):
    name: str
    domain: str
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    revenue: Optional[str] = None
    ai_score: Optional[int] = None
    ai_explanation: Optional[str] = None
    discovery_source: str = "Apollo"
    status: str = "discovered"
    hubspot_id: Optional[str] = None
    linkedin_url: Optional[str] = None

class CompanyCreate(CompanyBase):
    pass

class CompanyResponse(CompanyBase):
    id: int
    created_at: datetime
    updated_at: datetime
    contacts: List[ContactResponse] = []

    model_config = ConfigDict(from_attributes=True)

# --- Workflow Execution Trigger & Status ---
class TargetCompanyRequest(BaseModel):
    name: Optional[str] = None
    website_or_domain: Optional[str] = None
    linkedin_url: Optional[str] = None

class TargetBatchRequest(BaseModel):
    companies: List[TargetCompanyRequest]

class WorkflowTrigger(BaseModel):
    icp_config_id: Optional[int] = None

class SystemMetrics(BaseModel):
    total_companies: int
    qualified_companies: int
    total_contacts: int
    hubspot_synced_contacts: int
    hubspot_synced_companies: int
    average_ai_score: float
