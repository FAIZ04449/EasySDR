import json
import logging
from typing import Dict, Any, Tuple
from openai import OpenAI
from app.core.config import settings
from app.core.settings_helper import get_dynamic_setting

logger = logging.getLogger(__name__)

class AIQualificationService:
    def __init__(self):
        pass

    @property
    def api_key(self) -> str | None:
        return get_dynamic_setting("KIMI_API_KEY")

    @property
    def base_url(self) -> str | None:
        return get_dynamic_setting("KIMI_BASE_URL") or "https://api.moonshot.cn/v1"

    @property
    def model(self) -> str | None:
        return get_dynamic_setting("KIMI_MODEL") or "moonshot-v1-8k"

    @property
    def client(self) -> OpenAI | None:
        api_key = self.api_key
        base_url = self.base_url
        if api_key and api_key.lower() != "mock":
            return OpenAI(api_key=api_key, base_url=base_url)
        return None


    def qualify_company(self, company_name: str, domain: str, employee_count: int, industry: str, description: str = "", discovery_source: str = "Apollo") -> Tuple[int, str]:
        """
        Calls Kimi AI to evaluate company fit for EasySDR (B2B sales automation).
        Returns a score (0-100) and a concise explanation string.
        """
        # Fetch active ICP config & manual overrides from DB
        from app.core.database import SessionLocal
        from app.models.models import ICPConfig, UserFeedback
        
        db = SessionLocal()
        icp = None
        has_positive_feedback = False
        try:
            icp = db.query(ICPConfig).filter(ICPConfig.is_active == True).first()
            # Check if this company name was manually pushed in the past
            feedback = db.query(UserFeedback).filter(
                (UserFeedback.entity_type == "company_name") & 
                (UserFeedback.value == company_name)
            ).first()
            if feedback:
                has_positive_feedback = True
        except Exception as e:
            logger.error(f"Error querying database for ICP or Feedback in qualify_company: {str(e)}")
        finally:
            db.close()

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

        if not self.client:
            logger.info("Kimi API key not configured or set to mock. Using fallback rule-based AI scorer.")
            return self._fallback_company_scorer(company_name, industry, employee_count, discovery_source)

        prompt = f"""
        Evaluate the B2B sales target company:
        Name: {company_name}
        Domain: {domain}
        Employees: {employee_count}
        Industry: {industry}
        Description: {description}

        Target ICP Guidelines configured by the user:
        - Target Industry: {icp.industry}
        - Target Sub-vertical: {icp.sub_vertical}
        - Target Geography: {icp.geography}
        - Preferred Employee Range: {icp.min_employee} to {icp.max_employee} employees
        - Required Keywords: {icp.keywords}
        - Excluded Keywords: {icp.excluded_keywords}
        
        {"Note: This company was previously manually approved/synced by the user. Please prioritize this feedback and score it highly (95+)." if has_positive_feedback else ""}

        EasySDR provides autonomous prospecting, SDR systems, and workflows to target ICP matching the guidelines described above.
        Determine if this company is a high-potential buyer matching these targeting guidelines.
        
        Return a JSON object with exactly two fields:
        1. "score": An integer from 0 to 100 representing their ICP alignment.
        2. "explanation": A concise single-sentence summary of why they fit or do not fit.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional B2B lead generation assistant. You only output valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                timeout=15.0
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            score = int(data.get("score", 50))
            explanation = data.get("explanation", "Scored using Kimi AI pipeline.")
            
            # Boost if has manual push feedback
            if has_positive_feedback:
                score = max(score, 95)
                explanation = "Manual override boost applied. " + explanation
                
            return score, explanation
        except Exception as e:
            logger.error(f"Kimi AI API call failed: {str(e)}. Falling back to rules.")
            return self._fallback_company_scorer(company_name, industry, employee_count, discovery_source)

    def qualify_contact(self, name: str, title: str) -> str:
        """
        Classifies contact decision maker level: "high", "medium", or "low".
        High: CXO, VP, Owner, Founder, Head of Claims, Director of Claims.
        Medium: Claims Manager, Underwriting Lead, Operations Manager.
        Low: Analysts, Agents, Representatives, Coordinators.
        """
        if not title:
            return "low"
            
        title_lower = title.lower()
        
        # Check database for manual pushes of this title (improving accuracy/knowledge update)
        from app.core.database import SessionLocal
        from app.models.models import UserFeedback
        
        db = SessionLocal()
        is_manually_approved = False
        try:
            # Check if this exact title or a very close title was manually pushed before
            past_approvals = db.query(UserFeedback).filter(
                UserFeedback.entity_type == "contact_title"
            ).all()
            for app in past_approvals:
                if app.value.lower() in title_lower or title_lower in app.value.lower():
                    is_manually_approved = True
                    break
        except Exception as e:
            logger.error(f"Error querying contact feedback: {str(e)}")
        finally:
            db.close()

        if is_manually_approved:
            logger.info(f"Qualify contact: Title '{title}' boosted to 'high' based on user learning feedback history.")
            return "high"
        
        # High priority keywords
        high_keywords = ["ceo", "coo", "vp", "vice president", "director", "head of", "founder", "owner", "partner", "chief"]
        # Medium priority keywords
        med_keywords = ["manager", "lead", "specialist", "underwriter", "supervisor", "principal"]
        
        # Claims automation focus keywords
        claims_focus = ["claims", "operations", "digital", "transformation", "innovation", "technology"]

        # If it matches claims + high keywords
        if any(hk in title_lower for hk in high_keywords):
            if any(cf in title_lower for cf in claims_focus):
                return "high"
            return "medium" if "claims" not in title_lower else "high"
            
        if any(mk in title_lower for mk in med_keywords):
            return "medium"
            
        return "low"

    def _fallback_company_scorer(self, company_name: str, industry: str, employee_count: int, discovery_source: str = "Apollo") -> Tuple[int, str]:
        # Fetch active ICP config & manual overrides from DB
        from app.core.database import SessionLocal
        from app.models.models import ICPConfig, UserFeedback
        
        db = SessionLocal()
        icp = None
        feedback_boost = 0
        try:
            icp = db.query(ICPConfig).filter(ICPConfig.is_active == True).first()
            feedback = db.query(UserFeedback).filter(
                (UserFeedback.entity_type == "company_name") & 
                (UserFeedback.value == company_name)
            ).first()
            if feedback:
                feedback_boost = 30
        except Exception as e:
            logger.error(f"Error querying database for ICP or Feedback in fallback scorer: {str(e)}")
        finally:
            db.close()

        if not icp:
            icp = ICPConfig(
                industry="insurance",
                sub_vertical="MGA",
                geography="USA",
                min_employee=50,
                max_employee=2000,
                keywords="claims, underwriting, risk management, automation",
                excluded_keywords="healthcare, life insurance"
            )

        # Rule-based calculation dynamically matching active ICP
        score = 75 if discovery_source == "Direct Target" else 50
        reasons = []

        name_lower = company_name.lower()
        ind_lower = industry.lower() if industry else ""

        # 1. Industry match
        if icp.industry and (icp.industry.lower() in ind_lower or icp.industry.lower() in name_lower):
            score += 15
            reasons.append(f"Matches target industry '{icp.industry}'.")
            
        # 2. Sub-vertical match
        if icp.sub_vertical and (icp.sub_vertical.lower() in name_lower or icp.sub_vertical.lower() in ind_lower):
            score += 15
            reasons.append(f"Matches target sub-vertical '{icp.sub_vertical}'.")
            
        # 3. Size range matching
        if employee_count:
            if icp.min_employee <= employee_count <= icp.max_employee:
                score += 15
                reasons.append(f"Employee count ({employee_count}) matches target range ({icp.min_employee}-{icp.max_employee}).")
            elif employee_count < icp.min_employee:
                score -= 15
                reasons.append(f"Employee count ({employee_count}) is below target minimum ({icp.min_employee}).")
            else:
                score -= 5
                reasons.append(f"Employee count ({employee_count}) is above target maximum ({icp.max_employee}).")

        # 4. Keywords match
        if icp.keywords:
            keywords_list = [k.strip().lower() for k in icp.keywords.split(",") if k.strip()]
            matched_kws = []
            for kw in keywords_list:
                if kw in name_lower or kw in ind_lower:
                    score += 10
                    matched_kws.append(kw)
            if matched_kws:
                reasons.append(f"Matches keywords: {', '.join(matched_kws)}.")

        # 5. Excluded keywords match (disqualification)
        if icp.excluded_keywords:
            ex_list = [k.strip().lower() for k in icp.excluded_keywords.split(",") if k.strip()]
            matched_ex = []
            for ex in ex_list:
                if ex in name_lower or ex in ind_lower:
                    score -= 40
                    matched_ex.append(ex)
            if matched_ex:
                reasons.append(f"Contains excluded keywords: {', '.join(matched_ex)}.")

        # 6. Apply learning feedback boost
        if feedback_boost > 0:
            score += feedback_boost
            reasons.append("Applied feedback boost from previous manual overrides.")
            
        # Bounds check
        score = max(0, min(100, score))
        explanation = " ".join(reasons) if reasons else "Company is a moderately qualified target."
        return score, explanation

ai_qualification_service = AIQualificationService()
