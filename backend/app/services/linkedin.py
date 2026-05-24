import os
import json
import random
import time
import logging
from typing import List, Dict, Any
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)

# Directory to store session cookies
COOKIES_PATH = Path("C:/Users/KIIT0001/Desktop/Automation/backend/linkedin_cookies.json")

class LinkedInService:
    def __init__(self):
        self.username = settings.LINKEDIN_USERNAME
        self.password = settings.LINKEDIN_PASSWORD
        
        # Load user cookies from settings env if present
        if settings.LINKEDIN_COOKIES_JSON:
            try:
                cookies = json.loads(settings.LINKEDIN_COOKIES_JSON)
                self.save_cookies(cookies)
            except Exception as e:
                logger.error(f"Failed to load cookies from environment: {str(e)}")

    def save_cookies(self, cookies: List[Dict[str, Any]]):
        try:
            with open(COOKIES_PATH, "w") as f:
                json.dump(cookies, f)
            logger.info("LinkedIn cookies saved successfully.")
        except Exception as e:
            logger.error(f"Failed to save cookies to file: {str(e)}")

    def load_cookies(self) -> List[Dict[str, Any]]:
        if COOKIES_PATH.exists():
            try:
                with open(COOKIES_PATH, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to read cookies from file: {str(e)}")
        return []

    def extract_employees(self, company_name: str, domain: str) -> List[Dict[str, Any]]:
        """
        Launches Playwright to find decision-makers for a given company name.
        Uses cached cookies if available, otherwise attempts credentials login.
        If no credentials or cookies, returns high-quality mock data to prevent blocking.
        """
        # If no credentials/cookies are set, use mock data.
        cookies_list = self.load_cookies()
        if not cookies_list and not (self.username and self.password):
            logger.warning("No LinkedIn credentials or cookies found. Running in simulated fallback mode.")
            return self._generate_simulated_employees(company_name, domain)

        try:
            # We import playwright here to avoid errors if playwright hasn't finished installing via pip yet
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright is not installed yet. Using simulated fallback mode.")
            return self._generate_simulated_employees(company_name, domain)

        scraped_employees = []
        
        try:
            with sync_playwright() as p:
                # Launch headful/headless based on preferences (headless is safer for background, headful is good for debug)
                browser = p.chromium.launch(headless=True)
                
                # Create context with a standard desktop user agent
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                
                # Load cookies
                if cookies_list:
                    context.add_cookies(cookies_list)
                    logger.info("Loaded cached LinkedIn session cookies.")
                
                page = context.new_page()
                
                # Random viewport
                page.set_viewport_size({"width": random.randint(1280, 1440), "height": random.randint(720, 900)})
                
                # Check login status
                page.goto("https://www.linkedin.com/feed/", wait_until="networkidle")
                self._human_delay(2.0, 4.0)
                
                # If redirected to login page, cookies are expired
                if "login" in page.url or "checkpoint" in page.url:
                    logger.warning("LinkedIn cookies expired or invalid. Attempting credential-based login.")
                    if self.username and self.password:
                        page.goto("https://www.linkedin.com/login", wait_until="networkidle")
                        page.fill("#username", self.username)
                        self._human_delay(0.5, 1.5)
                        page.fill("#password", self.password)
                        self._human_delay(0.5, 1.5)
                        page.click("button[type='submit']")
                        page.wait_for_url("https://www.linkedin.com/feed/**", timeout=20000)
                        
                        # Save new cookies
                        new_cookies = context.cookies()
                        self.save_cookies(new_cookies)
                        logger.info("Successfully logged in to LinkedIn and saved cookies.")
                    else:
                        logger.error("No valid credentials found. Cannot login to LinkedIn.")
                        browser.close()
                        return self._generate_simulated_employees(company_name, domain)

                # Search for the company
                logger.info(f"Searching LinkedIn for company: {company_name}")
                search_query = f"{company_name} decision makers"
                encoded_query = search_query.replace(" ", "%20")
                page.goto(f"https://www.linkedin.com/search/results/people/?keywords={encoded_query}", wait_until="networkidle")
                self._human_delay(3.0, 5.0)

                # Extract contacts from people search page
                # Dynamic Selector search
                profile_cards = page.query_selector_all(".reusable-search__result-container")
                if not profile_cards:
                    # Fallback selectors
                    profile_cards = page.query_selector_all("li.entity-result")

                logger.info(f"Found {len(profile_cards)} potential profile cards on the LinkedIn search page.")
                
                for card in profile_cards[:5]:  # Limit to top 5 contacts for safety/MVP
                    try:
                        title_elem = card.query_selector(".entity-result__title-text a")
                        if not title_elem:
                            continue
                            
                        name_text = title_elem.inner_text().split("\n")[0].strip()
                        profile_url = title_elem.get_attribute("href")
                        # Strip tracking query params
                        if profile_url and "?" in profile_url:
                            profile_url = profile_url.split("?")[0]

                        subtitle_elem = card.query_selector(".entity-result__primary-subtitle")
                        title = subtitle_elem.inner_text().strip() if subtitle_elem else "Decision Maker"

                        # Ensure it's not a dummy contact
                        if "LinkedIn Member" in name_text:
                            continue

                        # Parse name and email domain mapping
                        email = f"{name_text.lower().replace(' ', '.')}@{domain}"

                        scraped_employees.append({
                            "name": name_text,
                            "title": title,
                            "linkedin_url": profile_url,
                            "email": email,
                            "phone": None,
                            "confidence_score": 65  # Verified via LinkedIn but needs email verification
                        })
                    except Exception as card_err:
                        logger.error(f"Error parsing profile card: {str(card_err)}")

                browser.close()
                
        except Exception as e:
            logger.error(f"LinkedIn Playwright scraping failed: {str(e)}")
            return self._generate_simulated_employees(company_name, domain)

        if not scraped_employees:
            logger.info("Playwright scraping yielded 0 contacts. Returning simulated contacts.")
            return self._generate_simulated_employees(company_name, domain)

        return scraped_employees

    def _human_delay(self, min_s: float = 1.0, max_s: float = 3.0):
        time.sleep(random.uniform(min_s, max_s))

    def _generate_simulated_employees(self, company_name: str, domain: str) -> List[Dict[str, Any]]:
        """
        Generates simulated high-quality contact records mimicking Playwright output.
        """
        # Formulate roles targeted for EasySDR (SDR automation)
        names = ["Rachel Adams", "Jonathan Vance", "Ashley Miller", "Marcus Cole"]
        titles = [
            "Chief Operations Officer",
            "Head of Claims Transformation",
            "VP of Insurance Operations",
            "VP of Underwriting & Claims"
        ]
        
        results = []
        for i, name in enumerate(names):
            clean_name = name.lower().replace(" ", "-")
            results.append({
                "name": name,
                "title": titles[i],
                "linkedin_url": f"https://www.linkedin.com/in/{clean_name}-easysdr-simulated",
                "email": f"{name.lower().replace(' ', '.')}@{domain}",
                "phone": f"+1 (800) 555-{1000 + i:04d}",
                "confidence_score": 65
            })
        return results

linkedin_service = LinkedInService()
