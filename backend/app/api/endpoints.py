from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from app.core.database import get_db
from app.models.models import Company, Contact, ICPConfig, SyncLog, ScrapingSession
from app.schemas.schemas import (
    ICPConfigCreate, ICPConfigResponse,
    CompanyResponse, ContactResponse,
    WorkflowTrigger, SystemMetrics, TargetCompanyRequest, TargetBatchRequest
)
from app.services.workflow import workflow_orchestrator
from app.services.apollo import apollo_service

router = APIRouter()

# --- ICP Config Routes ---
@router.get("/icp", response_model=List[ICPConfigResponse])
def get_icp_configs(db: Session = Depends(get_db)):
    return db.query(ICPConfig).all()

@router.post("/icp", response_model=ICPConfigResponse)
def create_icp_config(config: ICPConfigCreate, db: Session = Depends(get_db)):
    # Deactivate other configs if this one is active
    if config.is_active:
        db.query(ICPConfig).update({ICPConfig.is_active: False})
        
    db_config = ICPConfig(**config.model_dump())
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config

# --- Company Routes ---
@router.get("/companies", response_model=List[CompanyResponse])
def get_companies(status: str = None, db: Session = Depends(get_db)):
    query = db.query(Company)
    if status:
        query = query.filter(Company.status == status)
    return query.order_by(Company.updated_at.desc()).all()

def extract_domain(url: str) -> str:
    url_clean = url.replace("http://", "").replace("https://", "").replace("www.", "")
    url_clean = url_clean.split("/")[0]
    url_clean = url_clean.split("?")[0]
    return url_clean.strip()

def resolve_target_inputs(request: TargetCompanyRequest, db: Session) -> tuple[str, str, str | None]:
    """
    Parses and resolves the name, website domain, and optional linkedin url for the target request.
    Returns: (name, domain, linkedin_url)
    """
    name = (request.name or "").strip()
    website = (request.website_or_domain or "").strip()
    li_url = (request.linkedin_url or "").strip()
    
    # 1. Check if the website_or_domain is actually a LinkedIn Company URL
    if "linkedin.com/company/" in website.lower():
        if not li_url:
            li_url = website
        website = ""
        
    # 2. Extract handle from LinkedIn URL if provided
    handle = ""
    if li_url and "linkedin.com/company/" in li_url.lower():
        parts = li_url.split("linkedin.com/company/")
        if len(parts) > 1:
            handle = parts[1].split("/")[0].split("?")[0].strip()
            
    # 3. Resolve Domain & Name
    domain = ""
    if website:
        domain = extract_domain(website)
        
    if domain:
        if not name:
            name = domain.split(".")[0].title()
    else:
        # Try to resolve domain using LinkedIn handle
        if handle:
            results = apollo_service.search_external_companies(handle)
            if results:
                domain = results[0]["domain"]
                if not name:
                    name = results[0]["name"]
                if not li_url:
                    li_url = results[0]["linkedin_url"]
            else:
                domain = f"{handle.replace('-company', '')}.com"
                if not name:
                    name = handle.replace("-", " ").title()
        elif name:
            # We only have a company name! Resolve domain by searching Apollo
            results = apollo_service.search_external_companies(name)
            if results:
                domain = results[0]["domain"]
                name = results[0]["name"]
                li_url = results[0]["linkedin_url"] or li_url
            else:
                domain = f"{name.lower().replace(' ', '')}.com"
                
    if not domain:
        domain = "unknown.com"
    if not name:
        name = "Unknown Company"
        
    return name, domain, li_url or None

@router.post("/companies/target", response_model=CompanyResponse)
def target_company(request: TargetCompanyRequest, db: Session = Depends(get_db)):
    if not request.website_or_domain and not request.linkedin_url and not request.name:
        raise HTTPException(status_code=400, detail="Must provide at least a website domain, LinkedIn URL, or company name.")
        
    name, domain, linkedin_url = resolve_target_inputs(request, db)
    
    # Check for existing company
    company = db.query(Company).filter(Company.domain == domain).first()
    if company:
        company.status = "discovered"
        company.name = name
        company.linkedin_url = linkedin_url or company.linkedin_url
        company.ai_score = None
        company.ai_explanation = None
        db.commit()
        db.refresh(company)
    else:
        company = Company(
            name=name,
            domain=domain,
            linkedin_url=linkedin_url,
            discovery_source="Direct Target",
            status="discovered"
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        
    # Trigger pipeline async for this targeted company
    workflow_orchestrator.run_prospecting_pipeline_async(company_id=company.id)
    return company

@router.post("/companies/target-batch", response_model=List[CompanyResponse])
def target_companies_batch(batch: TargetBatchRequest, db: Session = Depends(get_db)):
    results = []
    for request in batch.companies:
        if not request.website_or_domain and not request.linkedin_url and not request.name:
            continue
            
        name, domain, linkedin_url = resolve_target_inputs(request, db)
        
        company = db.query(Company).filter(Company.domain == domain).first()
        if company:
            company.status = "discovered"
            company.name = name
            company.linkedin_url = linkedin_url or company.linkedin_url
            company.ai_score = None
            company.ai_explanation = None
            db.commit()
            db.refresh(company)
        else:
            company = Company(
                name=name,
                domain=domain,
                linkedin_url=linkedin_url,
                discovery_source="Direct Target",
                status="discovered"
            )
            db.add(company)
            db.commit()
            db.refresh(company)
        results.append(company)
        
    # Trigger pipeline async to process all pending companies
    workflow_orchestrator.run_prospecting_pipeline_async()
    return results

@router.get("/companies/search-external", response_model=List[Dict[str, Any]])
def search_external_companies(query: str, db: Session = Depends(get_db)):
    if not query or len(query.strip()) < 2:
        return []
    return apollo_service.search_external_companies(query.strip())

# --- Contact Routes ---
@router.get("/contacts", response_model=List[ContactResponse])
def get_contacts(status: str = None, db: Session = Depends(get_db)):
    query = db.query(Contact)
    if status:
        query = query.filter(Contact.status == status)
    return query.order_by(Contact.confidence_score.desc()).all()

# --- Pipeline Trigger & Status Routes ---
@router.post("/workflows/trigger")
def trigger_pipeline(trigger: WorkflowTrigger, background_tasks: BackgroundTasks):
    """
    Triggers the prospecting pipeline in the background.
    """
    workflow_orchestrator.run_prospecting_pipeline_async(icp_config_id=trigger.icp_config_id)
    return {"status": "triggered", "message": "Prospecting workflow started in background."}

@router.get("/workflows/status")
def get_pipeline_status():
    """
    Returns active running background jobs.
    """
    return workflow_orchestrator.get_active_jobs()

@router.get("/logs", response_model=List[Dict[str, Any]])
def get_scraping_logs(db: Session = Depends(get_db)):
    sessions = db.query(ScrapingSession).order_by(ScrapingSession.started_at.desc()).limit(10).all()
    return [
        {
            "id": s.id,
            "platform": s.platform,
            "status": s.status,
            "started_at": s.started_at.isoformat(),
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "logs": s.logs
        }
        for s in sessions
    ]

# --- Dashboard Metrics Route ---
@router.get("/metrics", response_model=SystemMetrics)
def get_system_metrics(db: Session = Depends(get_db)):
    total_companies = db.query(Company).count()
    qualified_companies = db.query(Company).filter(Company.status == "qualified").count() + db.query(Company).filter(Company.status == "synced").count()
    total_contacts = db.query(Contact).count()
    hubspot_synced_contacts = db.query(Contact).filter(Contact.status == "synced").count()
    hubspot_synced_companies = db.query(Company).filter(Company.status == "synced").count()
    
    # Calculate average AI score
    avg_score_query = db.query(Company.ai_score).filter(Company.ai_score != None).all()
    avg_score = 0.0
    if avg_score_query:
        scores = [q[0] for q in avg_score_query]
        avg_score = sum(scores) / len(scores)

    return SystemMetrics(
        total_companies=total_companies,
        qualified_companies=qualified_companies,
        total_contacts=total_contacts,
        hubspot_synced_contacts=hubspot_synced_contacts,
        hubspot_synced_companies=hubspot_synced_companies,
        average_ai_score=round(avg_score, 1)
    )

@router.post("/contacts/{contact_id}/sync", response_model=ContactResponse)
def force_sync_contact(contact_id: int, db: Session = Depends(get_db)):
    from app.models.models import UserFeedback
    from app.services.hubspot import hubspot_service

    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found.")
        
    company = db.query(Company).filter(Company.id == contact.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Associated company not found.")

    # 1. Record feedback: save approved title and company domain/name in UserFeedback table for machine learning / training
    if contact.title:
        title_feedback = db.query(UserFeedback).filter(
            (UserFeedback.entity_type == "contact_title") & 
            (UserFeedback.value == contact.title)
        ).first()
        if not title_feedback:
            db.add(UserFeedback(
                entity_type="contact_title",
                value=contact.title,
                feedback_type="manual_push"
            ))
            
    company_feedback = db.query(UserFeedback).filter(
        (UserFeedback.entity_type == "company_name") & 
        (UserFeedback.value == company.name)
    ).first()
    if not company_feedback:
        db.add(UserFeedback(
            entity_type="company_name",
            value=company.name,
            feedback_type="manual_push"
        ))

    db.commit()

    # 2. Sync Company to HubSpot if not synced
    if company.status != "synced" or not company.hubspot_id:
        hubspot_company_id, is_new_co = hubspot_service.sync_company(
            name=company.name,
            domain=company.domain,
            employee_count=company.employee_count or 100,
            ai_score=company.ai_score or 100,
            explanation=company.ai_explanation or "Manually pushed by user override."
        )
        company.hubspot_id = hubspot_company_id
        company.status = "synced"
        db.commit()
        hubspot_service.create_ai_summary_note(hubspot_company_id, company.ai_explanation or "Manually pushed by user override.")
    else:
        hubspot_company_id = company.hubspot_id

    # 3. Force Sync Contact to HubSpot
    try:
        hubspot_contact_id, is_new_c = hubspot_service.sync_contact(
            name=contact.name,
            email=contact.email or f"{contact.name.lower().replace(' ', '.')}@{company.domain}",
            title=contact.title,
            phone=contact.phone,
            linkedin_url=contact.linkedin_url,
            hubspot_company_id=hubspot_company_id
        )
        contact.hubspot_id = hubspot_contact_id
        contact.status = "synced"
        
        sync_c_log = SyncLog(
            entity_type="contact",
            entity_id=contact.id,
            hubspot_id=hubspot_contact_id,
            status="success"
        )
        db.add(sync_c_log)
        db.commit()
        db.refresh(contact)
        return contact
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"HubSpot sync failed: {str(e)}")

