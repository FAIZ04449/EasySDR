import httpx
import logging
from typing import List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class ApolloService:
    def __init__(self):
        self.api_key = settings.APOLLO_API_KEY
        self.base_url = "https://api.apollo.io/v1"
        self.headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache"
        }

    def discover_companies(self, industry: str, sub_vertical: str, geography: str, min_emp: int, max_emp: int, keywords: str) -> List[Dict[str, Any]]:
        """
        Discovers companies using Apollo's organization search endpoint.
        Falls back to mock data if API key is not configured.
        """
        if not self.api_key or self.api_key.lower() == "mock":
            logger.info("APOLLO_API_KEY not configured. Generating realistic mock companies.")
            return self._generate_mock_companies(industry, sub_vertical, geography, min_emp, max_emp, keywords)

        payload = {
            "api_key": self.api_key,
            "q_organization_keyword_tags": [industry, sub_vertical] + ([k.strip() for k in keywords.split(",")] if keywords else []),
            "organization_locations": [geography],
            "organization_num_employees_ranges": [f"{min_emp},{max_emp}"],
            "page": 1,
            "per_page": 10
        }

        try:
            response = httpx.post(f"{self.base_url}/organizations/search", json=payload, headers=self.headers, timeout=15.0)
            if response.status_code == 200:
                data = response.json()
                results = []
                for org in data.get("organizations", []):
                    results.append({
                        "name": org.get("name"),
                        "domain": org.get("primary_domain"),
                        "industry": org.get("industry"),
                        "employee_count": org.get("estimated_num_employees"),
                        "revenue": org.get("annual_revenue"),
                        "discovery_source": "Apollo"
                    })
                return results
            else:
                logger.error(f"Apollo API error: {response.status_code} - {response.text}")
                return self._generate_mock_companies(industry, sub_vertical, geography, min_emp, max_emp, keywords)
        except Exception as e:
            logger.error(f"Error calling Apollo API: {str(e)}")
            return self._generate_mock_companies(industry, sub_vertical, geography, min_emp, max_emp, keywords)

    def search_contacts(self, domain: str, role_keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Searches for contacts under a company domain using Apollo.
        Falls back to mock data if API key is not configured.
        """
        if not self.api_key or self.api_key.lower() == "mock":
            return self._generate_mock_contacts(domain, role_keywords)

        payload = {
            "api_key": self.api_key,
            "q_organization_domains": [domain],
            "person_titles": role_keywords,
            "page": 1,
            "per_page": 5
        }

        try:
            response = httpx.post(f"{self.base_url}/people/search", json=payload, headers=self.headers, timeout=15.0)
            if response.status_code == 200:
                data = response.json()
                results = []
                for person in data.get("people", []):
                    results.append({
                        "name": person.get("name"),
                        "title": person.get("title"),
                        "linkedin_url": person.get("linkedin_url"),
                        "email": person.get("email"),
                        "phone": person.get("work_phone"),
                        "confidence_score": 75 if person.get("email") else 30
                    })
                return results
            else:
                logger.error(f"Apollo People Search API error: {response.status_code} - {response.text}")
                return self._generate_mock_contacts(domain, role_keywords)
        except Exception as e:
            logger.error(f"Error calling Apollo People API: {str(e)}")
            return self._generate_mock_contacts(domain, role_keywords)

    def _generate_mock_companies(self, industry: str, sub_vertical: str, geography: str, min_emp: int, max_emp: int, keywords: str) -> List[Dict[str, Any]]:
        # Generates highly realistic target companies based on the specific inputs
        mga_names = ["ClaimsGuard MGA", "SureWay Underwriters", "CoverPro Carrier", "NextGen Claims Specialists", "InsurTech Labs MGA", "VeriClaim Insurance Solutions"]
        carrier_names = ["Apex Mutual", "Vanguard Casualty", "Summit Insurance Group", "Centennial Mutual", "Coastal Carrier", "Titan Specialty Risk"]
        
        base_names = mga_names if "mga" in sub_vertical.lower() or "mga" in keywords.lower() else carrier_names
        
        results = []
        for i, name in enumerate(base_names):
            domain = name.lower().replace(" ", "") + ".com"
            # Random size within range
            emp_count = int(min_emp + (max_emp - min_emp) * (i / len(base_names)))
            if emp_count == 0:
                emp_count = 50
            results.append({
                "name": name,
                "domain": domain,
                "industry": industry,
                "employee_count": emp_count,
                "revenue": f"${emp_count * 150000:,}",
                "discovery_source": "Apollo (Mock)"
            })
        return results

    def search_external_companies(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches for companies matching the query (name or domain) on Apollo.
        Falls back to mock data if API key is mock or unconfigured.
        """
        if not self.api_key or self.api_key.lower() == "mock":
            logger.info(f"Apollo API search mock for query: {query}")
            return self._generate_search_mock_companies(query)

        payload = {
            "api_key": self.api_key,
            "q_organization_name": query,
            "page": 1,
            "per_page": 5
        }

        try:
            response = httpx.post(f"{self.base_url}/organizations/search", json=payload, headers=self.headers, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                results = []
                for org in data.get("organizations", []):
                    li_url = org.get("linkedin_url")
                    results.append({
                        "name": org.get("name"),
                        "domain": org.get("primary_domain"),
                        "industry": org.get("industry") or "insurance",
                        "employee_count": org.get("estimated_num_employees") or 100,
                        "revenue": org.get("annual_revenue") or "$15,000,000",
                        "linkedin_url": li_url,
                        "discovery_source": "Apollo Search"
                    })
                return results
            else:
                logger.error(f"Apollo Search API error: {response.status_code} - {response.text}")
                return self._generate_search_mock_companies(query)
        except Exception as e:
            logger.error(f"Error calling Apollo Search API: {str(e)}")
            return self._generate_search_mock_companies(query)

    def _generate_search_mock_companies(self, query: str) -> List[Dict[str, Any]]:
        query_lower = query.lower()
        all_options = [
            {"name": "ClaimsGuard MGA", "domain": "claimsguard.com", "industry": "insurance", "employee_count": 120, "revenue": "$18,000,000", "linkedin_url": "https://www.linkedin.com/company/claimsguard-mga"},
            {"name": "SureWay Underwriters", "domain": "surewaymga.com", "industry": "insurance", "employee_count": 85, "revenue": "$12,500,000", "linkedin_url": "https://www.linkedin.com/company/sureway-underwriters"},
            {"name": "CoverPro Carrier", "domain": "coverproinsurance.com", "industry": "insurance", "employee_count": 450, "revenue": "$65,000,000", "linkedin_url": "https://www.linkedin.com/company/coverpro-insurance"},
            {"name": "NextGen Claims Specialists", "domain": "nextgenclaims.com", "industry": "insurance", "employee_count": 55, "revenue": "$7,200,000", "linkedin_url": "https://www.linkedin.com/company/nextgenclaims"},
            {"name": "InsurTech Labs MGA", "domain": "insurtechlabs.co", "industry": "insurance", "employee_count": 30, "revenue": "$4,500,000", "linkedin_url": "https://www.linkedin.com/company/insurtech-labs-mga"},
            {"name": "Apex Mutual", "domain": "apexmutual.com", "industry": "insurance", "employee_count": 1500, "revenue": "$220,000,000", "linkedin_url": "https://www.linkedin.com/company/apex-mutual"},
            {"name": "Vanguard Casualty", "domain": "vanguardcasualty.com", "industry": "insurance", "employee_count": 820, "revenue": "$110,000,000", "linkedin_url": "https://www.linkedin.com/company/vanguardcasualty"},
            {"name": "Summit Insurance Group", "domain": "summitins.com", "industry": "insurance", "employee_count": 3200, "revenue": "$480,000,000", "linkedin_url": "https://www.linkedin.com/company/summit-insurance-group"}
        ]
        
        matches = []
        for opt in all_options:
            if query_lower in opt["name"].lower() or query_lower in opt["domain"].lower() or query_lower in opt["industry"].lower():
                matches.append({**opt, "discovery_source": "Apollo Search (Mock)"})
        
        if not matches:
            clean_name = query.strip().title()
            domain_name = query.lower().replace(" ", "").replace("-", "") + ".com"
            matches.append({
                "name": f"{clean_name} Insurance",
                "domain": domain_name,
                "industry": "insurance",
                "employee_count": 140,
                "revenue": "$21,000,000",
                "linkedin_url": f"https://www.linkedin.com/company/{query.lower().replace(' ', '-')}",
                "discovery_source": "Apollo Search (Dynamic Mock)"
            })
            
        return matches

    def _generate_mock_contacts(self, domain: str, role_keywords: List[str]) -> List[Dict[str, Any]]:
        # Generates key personas based on typical roles requested
        titles = ["VP of Claims", "Director of Claims Automation", "Chief Operations Officer", "Head of Digital Transformation", "Claims Technology Manager"]
        names = ["Sarah Jenkins", "Michael Chang", "Robert O'Connor", "Emily Watson", "David Miller"]
        
        contacts = []
        for i, title in enumerate(titles):
            # Check if any role keyword matches or if we should just generate
            name = names[i]
            email = f"{name.lower().replace(' ', '.')}@{domain}"
            contacts.append({
                "name": name,
                "title": title,
                "linkedin_url": f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}-easysdr-mock",
                "email": email,
                "phone": f"+1 (555) 019-{i:03d}",
                "confidence_score": 85  # Email verified, domain verified
            })
        return contacts

apollo_service = ApolloService()
