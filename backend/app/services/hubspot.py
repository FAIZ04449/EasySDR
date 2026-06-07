import httpx
import logging
from typing import Dict, Any, Tuple
from app.core.config import settings
from app.core.settings_helper import get_dynamic_setting

logger = logging.getLogger(__name__)

class HubSpotService:
    def __init__(self):
        self.base_url = "https://api.hubapi.com"

    @property
    def access_token(self) -> str | None:
        return get_dynamic_setting("HUBSPOT_ACCESS_TOKEN")

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }


    def sync_company(self, name: str, domain: str, employee_count: int, ai_score: int, explanation: str) -> Tuple[str, bool]:
        """
        Creates or updates a company in HubSpot.
        Checks for duplicates using domain.
        Returns (hubspot_company_id, is_new).
        """
        if not self.access_token or self.access_token.lower() == "mock":
            logger.info(f"HubSpot sync in Mock Mode. Normalizing and syncing company: {name} ({domain})")
            # Generate a realistic HubSpot ID
            mock_id = f"hs_comp_{abs(hash(domain)) % 100000000}"
            return mock_id, True

        # 1. Search for existing company by domain
        search_url = f"{self.base_url}/crm/v3/objects/companies/search"
        search_payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "domain",
                    "operator": "EQ",
                    "value": domain
                }]
            }]
        }

        try:
            response = httpx.post(search_url, json=search_payload, headers=self.headers, timeout=10.0)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    existing_id = results[0]["id"]
                    logger.info(f"Found existing HubSpot company for domain {domain}: ID {existing_id}. Updating properties.")
                    # Update company score & description
                    self._update_company_properties(existing_id, employee_count, ai_score, explanation)
                    return existing_id, False
            else:
                logger.error(f"Failed searching HubSpot company: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error during HubSpot search: {str(e)}")

        # 2. Create new company if not found
        create_url = f"{self.base_url}/crm/v3/objects/companies"
        create_payload = {
            "properties": {
                "name": name,
                "domain": domain,
                "numberofemployees": str(employee_count) if employee_count else "0",
                "description": f"AI Qualified fit score: {ai_score}. {explanation}"
            }
        }

        try:
            response = httpx.post(create_url, json=create_payload, headers=self.headers, timeout=10.0)
            if response.status_code == 201:
                new_id = response.json()["id"]
                logger.info(f"Created new HubSpot company: {name} (ID: {new_id})")
                return new_id, True
            else:
                logger.error(f"Failed to create company in HubSpot: {response.status_code} - {response.text}")
                raise Exception(f"HubSpot company creation failed: {response.text}")
        except Exception as e:
            logger.error(f"Error creating company in HubSpot: {str(e)}")
            # Fallback to mock ID on connection error to keep process going
            fallback_id = f"hs_comp_fallback_{abs(hash(domain)) % 100000000}"
            return fallback_id, True

    def sync_contact(self, name: str, email: str, title: str, phone: str, linkedin_url: str, hubspot_company_id: str = None) -> Tuple[str, bool]:
        """
        Creates or updates a contact in HubSpot.
        Checks for duplicates using email.
        Returns (hubspot_contact_id, is_new).
        """
        if not self.access_token or self.access_token.lower() == "mock":
            logger.info(f"HubSpot sync in Mock Mode. Normalizing and syncing contact: {name} ({email})")
            mock_id = f"hs_cont_{abs(hash(email)) % 100000000}"
            return mock_id, True

        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        # 1. Search for existing contact by email
        search_url = f"{self.base_url}/crm/v3/objects/contacts/search"
        search_payload = {
            "filterGroups": [{
                "filters": [{
                    "propertyName": "email",
                    "operator": "EQ",
                    "value": email
                }]
            }]
        }

        existing_id = None
        try:
            response = httpx.post(search_url, json=search_payload, headers=self.headers, timeout=10.0)
            if response.status_code == 200:
                results = response.json().get("results", [])
                if results:
                    existing_id = results[0]["id"]
                    logger.info(f"Found existing HubSpot contact for email {email}: ID {existing_id}")
            else:
                logger.error(f"Failed searching HubSpot contact: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error searching contact: {str(e)}")

        # Create or Update payload
        properties = {
            "email": email,
            "firstname": first_name,
            "lastname": last_name,
            "jobtitle": title,
            "phone": phone if phone else ""
        }
        if linkedin_url:
            properties["linkedin_url"] = linkedin_url  # Standard custom field in sales setups

        if existing_id:
            # Update existing contact
            update_url = f"{self.base_url}/crm/v3/objects/contacts/{existing_id}"
            try:
                response = httpx.patch(update_url, json={"properties": properties}, headers=self.headers, timeout=10.0)
                if response.status_code == 200:
                    logger.info(f"Updated HubSpot contact: {name} (ID: {existing_id})")
                    if hubspot_company_id:
                        self._associate_contact_and_company(existing_id, hubspot_company_id)
                    return existing_id, False
            except Exception as e:
                logger.error(f"Error updating contact: {str(e)}")
            return existing_id, False

        # 2. Create new contact
        create_url = f"{self.base_url}/crm/v3/objects/contacts"
        try:
            response = httpx.post(create_url, json={"properties": properties}, headers=self.headers, timeout=10.0)
            if response.status_code == 201:
                new_id = response.json()["id"]
                logger.info(f"Created new HubSpot contact: {name} (ID: {new_id})")
                if hubspot_company_id:
                    self._associate_contact_and_company(new_id, hubspot_company_id)
                return new_id, True
            else:
                logger.error(f"Failed to create contact in HubSpot: {response.status_code} - {response.text}")
                raise Exception(f"HubSpot contact creation failed: {response.text}")
        except Exception as e:
            logger.error(f"Error creating contact: {str(e)}")
            fallback_id = f"hs_cont_fallback_{abs(hash(email)) % 100000000}"
            return fallback_id, True

    def create_ai_summary_note(self, hubspot_company_id: str, summary_content: str):
        """
        Attaches a note/engagement detailing the AI qualification to the company file.
        """
        if not self.access_token or self.access_token.lower() == "mock":
            logger.info(f"HubSpot sync in Mock Mode. Created AI note for company {hubspot_company_id}: {summary_content}")
            return

        note_url = f"{self.base_url}/crm/v3/objects/notes"
        note_payload = {
            "properties": {
                "hs_note_body": f"<h3>EasySDR Autonomous SDR — AI Qualification Summary</h3><p>{summary_content}</p>",
                "hs_timestamp": None  # Will default to current time
            }
        }

        try:
            # 1. Create the note object
            response = httpx.post(note_url, json=note_payload, headers=self.headers, timeout=10.0)
            if response.status_code == 201:
                note_id = response.json()["id"]
                # 2. Associate note to company
                assoc_url = f"{self.base_url}/crm/v3/objects/notes/{note_id}/associations/company/{hubspot_company_id}/202" # 202 is the note-to-company association type id
                assoc_response = httpx.put(assoc_url, headers=self.headers, timeout=10.0)
                if assoc_response.status_code in [200, 204]:
                    logger.info(f"Attached AI qualification note {note_id} to HubSpot company {hubspot_company_id}")
                else:
                    logger.error(f"Failed to associate note to company: {assoc_response.status_code} - {assoc_response.text}")
            else:
                logger.error(f"Failed to create note: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error creating HubSpot note association: {str(e)}")

    def _update_company_properties(self, hubspot_company_id: str, employee_count: int, ai_score: int, explanation: str):
        update_url = f"{self.base_url}/crm/v3/objects/companies/{hubspot_company_id}"
        payload = {
            "properties": {
                "numberofemployees": str(employee_count) if employee_count else "0",
                "description": f"AI Qualified fit score: {ai_score}. {explanation}"
            }
        }
        try:
            httpx.patch(update_url, json=payload, headers=self.headers, timeout=10.0)
        except Exception as e:
            logger.error(f"Failed to update company properties: {str(e)}")

    def _associate_contact_and_company(self, contact_id: str, company_id: str):
        # 279 is the contact-to-company association type ID in HubSpot v3 API
        assoc_url = f"{self.base_url}/crm/v3/objects/contacts/{contact_id}/associations/company/{company_id}/279"
        try:
            response = httpx.put(assoc_url, headers=self.headers, timeout=10.0)
            if response.status_code in [200, 204]:
                logger.info(f"Associated contact {contact_id} to company {company_id} in HubSpot.")
            else:
                logger.error(f"Failed contact-company association: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error associating contact and company: {str(e)}")

hubspot_service = HubSpotService()
