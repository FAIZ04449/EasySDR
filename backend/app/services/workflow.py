import threading
import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import Company, Contact, ICPConfig, SyncLog, ScrapingSession
from app.services.apollo import apollo_service
from app.services.linkedin import linkedin_service
from app.services.enrichment import enrichment_service
from app.services.ai_qualification import ai_qualification_service
from app.services.hubspot import hubspot_service
from app.services.datanyze import datanyze_service

logger = logging.getLogger(__name__)

# Active background workflows tracker
active_workflows = {}

class WorkflowOrchestrator:
    def __init__(self):
        self.lock = threading.Lock()

    def run_prospecting_pipeline_async(self, icp_config_id: int = None, company_id: int = None):
        """
        Runs the prospecting pipeline in a background thread.
        """
        thread = threading.Thread(
            target=self.run_prospecting_pipeline,
            args=(icp_config_id, company_id),
            daemon=True
        )
        thread.start()
        return thread

    def run_prospecting_pipeline(self, icp_config_id: int = None, company_id: int = None):
        """
        Synchronous execution loop for the prospecting pipeline.
        """
        job_id = f"job_{int(datetime.utcnow().timestamp())}"
        with self.lock:
            active_workflows[job_id] = {
                "status": "running",
                "stage": "started",
                "companies_processed": 0,
                "contacts_synced": 0,
                "started_at": datetime.utcnow().isoformat()
            }

        db = SessionLocal()
        
        # Log a scraping session
        scraping_session = ScrapingSession(platform="combined", status="running", logs="Job started.")
        db.add(scraping_session)
        db.commit()
        db.refresh(scraping_session)

        try:
            companies_to_process = []

            if company_id:
                company = db.query(Company).filter(Company.id == company_id).first()
                if not company:
                    msg = f"Target company ID {company_id} not found. Pipeline aborted."
                    logger.warning(msg)
                    self._update_job_status(job_id, "failed", "company_not_found")
                    scraping_session.status = "failed"
                    scraping_session.logs += f"\n{msg}"
                    scraping_session.ended_at = datetime.utcnow()
                    db.commit()
                    return
                companies_to_process.append(company)
                msg = f"Executing manual target pipeline for company: {company.name}"
                logger.info(msg)
                scraping_session.logs += f"\n{msg}"
            else:
                # 1. Fetch pending custom targeted companies in the database
                pending_companies = db.query(Company).filter(Company.status == "discovered").all()
                
                if not pending_companies:
                    msg = "No pending custom targeted companies found in queue. Querying active ICP configuration for automated Apollo discovery..."
                    logger.info(msg)
                    scraping_session.logs += f"\n{msg}"
                    self._update_job_status(job_id, "running", "querying_apollo_discovery")
                    
                    # Fetch active ICP config
                    icp = db.query(ICPConfig).filter(ICPConfig.is_active == True).first()
                    if not icp:
                        # Fallback default configuration if DB is empty
                        icp = ICPConfig(
                            industry="insurance",
                            sub_vertical="MGA",
                            geography="USA",
                            min_employee=50,
                            max_employee=2000,
                            keywords="claims, underwriting, risk management, automation",
                            excluded_keywords="healthcare, life insurance"
                        )
                    
                    try:
                        discovered_results = apollo_service.discover_companies(
                            industry=icp.industry,
                            sub_vertical=icp.sub_vertical,
                            geography=icp.geography,
                            min_emp=icp.min_employee,
                            max_emp=icp.max_employee,
                            keywords=icp.keywords or ""
                        )
                        
                        msg = f"Apollo organization search returned {len(discovered_results)} target companies."
                        logger.info(msg)
                        scraping_session.logs += f"\n{msg}"
                        
                        new_companies = []
                        for res in discovered_results:
                            # Check if domain already exists to avoid duplication
                            existing = db.query(Company).filter(Company.domain == res["domain"]).first()
                            if not existing:
                                co = Company(
                                    name=res["name"],
                                    domain=res["domain"],
                                    industry=res["industry"],
                                    employee_count=res["employee_count"],
                                    revenue=res["revenue"],
                                    discovery_source=res["discovery_source"],
                                    status="discovered"
                                )
                                db.add(co)
                                new_companies.append(co)
                                
                        if new_companies:
                            db.commit()
                            for co in new_companies:
                                db.refresh(co)
                            companies_to_process = new_companies
                            msg = f"Successfully queued {len(companies_to_process)} newly discovered companies for processing."
                            logger.info(msg)
                            scraping_session.logs += f"\n{msg}"
                        else:
                            msg = "Apollo discovery found 0 new companies (all matching domains already exist in lead database)."
                            logger.info(msg)
                            scraping_session.logs += f"\n{msg}"
                            scraping_session.status = "success"
                            scraping_session.ended_at = datetime.utcnow()
                            db.commit()
                            self._update_job_status(job_id, "completed", "no_new_targets")
                            return
                    except Exception as discovery_err:
                        msg = f"Apollo automated company discovery search failed: {str(discovery_err)}"
                        logger.error(msg)
                        scraping_session.logs += f"\n{msg}"
                        scraping_session.status = "failed"
                        scraping_session.ended_at = datetime.utcnow()
                        db.commit()
                        self._update_job_status(job_id, "failed", "discovery_failed")
                        return
                else:
                    companies_to_process = list(pending_companies)
                    msg = f"Starting automated prospecting pipeline for {len(companies_to_process)} custom targeted company accounts."
                    logger.info(msg)
                    scraping_session.logs += f"\n{msg}"
                    self._update_job_status(job_id, "running", "processing_custom_targets")


            companies_processed_count = 0
            contacts_synced_count = 0

            # 3. Process Each Company
            for company in companies_to_process:

                # Skip if already disqualified or synced (in standard run, let's process discovered ones)
                if company.status in ["disqualified", "synced"]:
                    continue

                msg = f"AI Qualifying Company: {company.name}"
                logger.info(msg)
                scraping_session.logs += f"\n{msg}"
                self._update_job_status(job_id, "running", f"qualifying_company_{company.name}")
                db.commit()

                # 4. AI Company Qualification
                ai_score, ai_explanation = ai_qualification_service.qualify_company(
                    company_name=company.name,
                    domain=company.domain,
                    employee_count=company.employee_count,
                    industry=company.industry,
                    description=f"{company.name} operating in {company.industry}.",
                    discovery_source=company.discovery_source
                )

                company.ai_score = ai_score
                company.ai_explanation = ai_explanation
                
                if ai_score < 70:
                    company.status = "disqualified"
                    msg = f"Disqualified {company.name} with score {ai_score} ({ai_explanation})"
                    logger.info(msg)
                    scraping_session.logs += f"\n{msg}"
                    db.commit()
                    continue
                
                company.status = "qualified"
                msg = f"Qualified {company.name} with score {ai_score} ({ai_explanation})"
                logger.info(msg)
                scraping_session.logs += f"\n{msg}"
                db.commit()

                # 5. Extract Decision Makers
                self._update_job_status(job_id, "running", f"extracting_employees_{company.name}")
                
                # Step 5A: Try Apollo search first
                role_keywords = ["Claims", "COO", "Operations", "Transformation", "Underwriting"]
                contacts_list = apollo_service.search_contacts(company.domain, role_keywords)

                # Step 5B: Supplementary Playwright extraction if Apollo is empty or missing data
                if not contacts_list:
                    msg = f"Apollo contacts empty for {company.name}. Initializing LinkedIn scraping layer."
                    logger.info(msg)
                    scraping_session.logs += f"\n{msg}"
                    db.commit()
                    contacts_list = linkedin_service.extract_employees(company.name, company.domain)

                msg = f"Retrieved {len(contacts_list)} potential target contacts."
                logger.info(msg)
                scraping_session.logs += f"\n{msg}"
                db.commit()

                # Sync Company to HubSpot first
                hubspot_company_id, is_new_co = hubspot_service.sync_company(
                    name=company.name,
                    domain=company.domain,
                    employee_count=company.employee_count,
                    ai_score=company.ai_score,
                    explanation=company.ai_explanation
                )
                company.hubspot_id = hubspot_company_id
                company.status = "synced"
                
                sync_co_log = SyncLog(
                    entity_type="company",
                    entity_id=company.id,
                    hubspot_id=hubspot_company_id,
                    status="success"
                )
                db.add(sync_co_log)
                db.commit()

                # Create AI Note summary on HubSpot
                hubspot_service.create_ai_summary_note(hubspot_company_id, company.ai_explanation)

                # 6. Enrich, Score, and Sync Contacts
                for c_data in contacts_list:
                    # Check if contact already exists for this company
                    contact = db.query(Contact).filter(
                        (Contact.company_id == company.id) & (
                            (Contact.email == c_data["email"]) | 
                            ((Contact.linkedin_url == c_data["linkedin_url"]) & (Contact.linkedin_url != None))
                        )
                    ).first()

                    if not contact:
                        contact = Contact(
                            company_id=company.id,
                            name=c_data["name"],
                            title=c_data["title"],
                            linkedin_url=c_data["linkedin_url"],
                            email=c_data["email"],
                            phone=c_data["phone"],
                            status="discovered"
                        )
                        db.add(contact)
                        db.commit()
                        db.refresh(contact)

                    if contact.status == "synced":
                        continue

                    # AI Rank title relevance
                    relevance = ai_qualification_service.qualify_contact(contact.name, contact.title)
                    if relevance == "low":
                        contact.status = "ignored"
                        db.commit()
                        continue

                    # 1. Primary lookup: Datanyze (emails & phone numbers)
                    datanyze_data = None
                    if not contact.email or not contact.phone:
                        msg = f"Enriching contact via Datanyze: {contact.name}"
                        logger.info(msg)
                        scraping_session.logs += f"\n{msg}"
                        datanyze_data = datanyze_service.enrich_contact(contact.name, contact.title or "", company.domain)
                    
                    if datanyze_data:
                        # Datanyze succeeded! Use found values to fill in missing details
                        if not contact.email:
                            contact.email = datanyze_data["email"]
                        if not contact.phone:
                            contact.phone = datanyze_data["phone"]
                        if datanyze_data["linkedin_url"] and not contact.linkedin_url:
                            contact.linkedin_url = datanyze_data["linkedin_url"]
                        contact.confidence_score = datanyze_data["confidence_score"]
                        msg = f"Datanyze enriched contact successfully: {contact.email} ({contact.phone})"
                        logger.info(msg)
                        scraping_session.logs += f"\n{msg}"
                    else:
                        # Datanyze failed or we already have email/phone (e.g. from Apollo or LinkedIn crawler)
                        msg = f"Running verification & scoring for contact: {contact.name}"
                        logger.info(msg)
                        scraping_session.logs += f"\n{msg}"
                        
                        enriched = enrichment_service.enrich_contact(
                            {"email": contact.email, "linkedin_url": contact.linkedin_url},
                            company.domain
                        )
                        contact.confidence_score = enriched["confidence_score"]

                    
                    if contact.confidence_score < 70:
                        contact.status = "ignored"
                        msg = f"Ignored contact {contact.name} due to low confidence score {contact.confidence_score}."
                        logger.info(msg)
                        scraping_session.logs += f"\n{msg}"
                        db.commit()
                        continue

                    # Push contact to HubSpot CRM
                    self._update_job_status(job_id, "running", f"syncing_contact_{contact.name}")
                    db.commit()
                    
                    try:
                        hubspot_contact_id, is_new_c = hubspot_service.sync_contact(
                            name=contact.name,
                            email=contact.email,
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
                        contacts_synced_count += 1
                        
                        msg = f"Synced contact {contact.name} to HubSpot CRM (ID: {hubspot_contact_id})"
                        logger.info(msg)
                        scraping_session.logs += f"\n{msg}"
                    except Exception as hs_err:
                        contact.status = "failed"
                        sync_c_log = SyncLog(
                            entity_type="contact",
                            entity_id=contact.id,
                            status="failed",
                            error_message=str(hs_err)
                        )
                        db.add(sync_c_log)
                        logger.error(f"HubSpot contact sync failed: {str(hs_err)}")
                        scraping_session.logs += f"\nHubSpot contact sync failed for {contact.name}: {str(hs_err)}"
                    
                    db.commit()

                companies_processed_count += 1
                with self.lock:
                    active_workflows[job_id]["companies_processed"] = companies_processed_count
                    active_workflows[job_id]["contacts_synced"] = contacts_synced_count

            scraping_session.status = "success"
            scraping_session.ended_at = datetime.utcnow()
            scraping_session.logs += "\nJob completed successfully."
            db.commit()
            
            self._update_job_status(job_id, "completed", "done", companies_processed_count, contacts_synced_count)

        except Exception as err:
            logger.error(f"Workflow execution failure: {str(err)}")
            scraping_session.status = "failed"
            scraping_session.logs += f"\nCritical system error: {str(err)}"
            scraping_session.ended_at = datetime.utcnow()
            db.commit()
            self._update_job_status(job_id, "failed", f"error: {str(err)}")
        finally:
            db.close()

    def _update_job_status(self, job_id: str, status: str, stage: str, companies: int = 0, contacts: int = 0):
        with self.lock:
            if job_id in active_workflows:
                active_workflows[job_id]["status"] = status
                active_workflows[job_id]["stage"] = stage
                if companies:
                    active_workflows[job_id]["companies_processed"] = companies
                if contacts:
                    active_workflows[job_id]["contacts_synced"] = contacts

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        with self.lock:
            return active_workflows.get(job_id, {"status": "unknown"})

    def get_active_jobs(self) -> Dict[str, Any]:
        with self.lock:
            return dict(active_workflows)

workflow_orchestrator = WorkflowOrchestrator()
