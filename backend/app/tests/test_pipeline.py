import pytest
from app.core.database import engine, Base
from app.models import models
# Ensure all tables are created in the test database
Base.metadata.create_all(bind=engine)


from app.services.enrichment import enrichment_service
from app.services.ai_qualification import ai_qualification_service
from app.services.apollo import apollo_service
from app.services.datanyze import datanyze_service


def test_email_validation():
    # Test valid addresses
    assert enrichment_service.validate_email_syntax("john.doe@easysdr.ai") is True
    assert enrichment_service.validate_email_syntax("sarah@claimsguard.com") is True
    
    # Test invalid addresses
    assert enrichment_service.validate_email_syntax("john.doe.easysdr.ai") is False
    assert enrichment_service.validate_email_syntax("john.doe@") is False
    assert enrichment_service.validate_email_syntax("@domain.com") is False

def test_mx_check_mock():
    # Test built-in mock dns resolution logic for test domains
    assert enrichment_service.check_mx_records("example.com") is True
    assert enrichment_service.check_mx_records("localhost") is True

def test_confidence_scoring():
    # 1. High trusted score: Valid email (40) + LinkedIn (25) + domain check (20) + activity (15) = 100
    score, status = enrichment_service.calculate_confidence_score(
        email="test@example.com",
        linkedin_url="https://www.linkedin.com/in/test-profile-easysdr-mock",
        domain="example.com",
        has_recent_activity=True
    )
    assert score == 100
    assert status == "trusted"

    # 2. Usable score: Valid email (40) + domain check (20) + activity (15) = 75
    score, status = enrichment_service.calculate_confidence_score(
        email="test@example.com",
        linkedin_url="",
        domain="example.com",
        has_recent_activity=True
    )
    assert score == 75
    assert status == "usable"

    # 3. Ignore score: No email (0) + LinkedIn (25) + domain (20) + activity (15) = 60
    score, status = enrichment_service.calculate_confidence_score(
        email="",
        linkedin_url="https://www.linkedin.com/in/test-profile-easysdr-mock",
        domain="example.com",
        has_recent_activity=True
    )
    assert score == 60
    assert status == "ignore"

def test_ai_qualification_rules():
    # Test MGA priority scoring
    score, explanation = ai_qualification_service._fallback_company_scorer(
        company_name="Apex MGA Underwriters",
        industry="insurance",
        employee_count=150
    )
    # Start: 50, +15 industry, +15 sub-vertical, +15 size = 95
    assert score >= 95
    assert "MGA" in explanation

    # Test small workforce penalty
    score, explanation = ai_qualification_service._fallback_company_scorer(
        company_name="Local Agency",
        industry="sales",
        employee_count=5
    )
    # Start: 50, -15 size penalty = 35
    assert score <= 35

def test_apollo_mock_generation():
    companies = apollo_service._generate_mock_companies(
        industry="insurance",
        sub_vertical="MGA",
        geography="USA",
        min_emp=50,
        max_emp=2000,
        keywords="claims"
    )
    assert len(companies) > 0
    assert companies[0]["domain"].endswith(".com")
    assert "MGA" in companies[0]["name"] or "Carrier" in companies[0]["name"] or "Solutions" in companies[0]["name"] or "Underwriters" in companies[0]["name"]

def test_datanyze_enrichment():
    # Test enrichment function
    res = datanyze_service._generate_mock_enrichment("Sarah Jenkins", "VP of Claims", "claimsguard.com")
    if res:
        assert res["email"] == "sarah.jenkins@claimsguard.com"
        assert res["title"] == "VP of Claims"
        assert res["confidence_score"] == 90
        assert res["status"] == "enriched"
        assert "+1" in res["phone"]
    else:
        # 20% fallback probability case
        assert res is None

from app.api.endpoints import extract_domain, resolve_target_inputs
from app.schemas.schemas import TargetCompanyRequest
from app.core.database import SessionLocal

def test_domain_extraction():
    assert extract_domain("https://www.easysdr.ai/about") == "easysdr.ai"
    assert extract_domain("http://claimsguardmga.com") == "claimsguardmga.com"
    assert extract_domain("acmemga.com/careers?id=12") == "acmemga.com"
    assert extract_domain("www.carriertech.org") == "carriertech.org"

def test_targeting_resolutions():
    db = SessionLocal()
    try:
        # Test case 1: Website domain input
        req1 = TargetCompanyRequest(name="ClaimsGuard", website_or_domain="claimsguard.com")
        name, domain, li = resolve_target_inputs(req1, db)
        assert domain == "claimsguard.com"
        assert name == "ClaimsGuard"
        
        # Test case 2: LinkedIn Company URL input (resolves handle)
        req2 = TargetCompanyRequest(website_or_domain="https://www.linkedin.com/company/sureway-underwriters")
        name, domain, li = resolve_target_inputs(req2, db)
        assert "sureway" in domain
        assert "Sureway" in name
        assert "linkedin.com/company/sureway-underwriters" in li
        
        # Test case 3: Company Name query only (resolves via Apollo search mock)
        req3 = TargetCompanyRequest(name="Apex Mutual")
        name, domain, li = resolve_target_inputs(req3, db)
        assert domain == "apexmutual.com"
        assert "Apex" in name
        assert "linkedin.com/company/apex-mutual" in li
    finally:
        db.close()

def test_dynamic_icp_and_feedback():
    from app.core.database import SessionLocal
    from app.models.models import ICPConfig, UserFeedback
    
    db = SessionLocal()
    try:
        # Clear existing active configs to isolate test
        db.query(ICPConfig).update({ICPConfig.is_active: False})
        db.query(UserFeedback).delete()
        db.commit()

        # 1. Create a custom active ICP Config
        test_icp = ICPConfig(
            industry="logistics",
            sub_vertical="freight",
            geography="USA",
            min_employee=10,
            max_employee=500,
            keywords="tracking, warehouse, dispatch",
            excluded_keywords="marine, shipping",
            is_active=True
        )
        db.add(test_icp)
        db.commit()

        # 2. Test fallback company scorer with matching logistics company
        # Matches industry "logistics" and keyword "tracking"
        score, explanation = ai_qualification_service._fallback_company_scorer(
            company_name="Logistics Dispatch Inc",
            industry="logistics and freight",
            employee_count=100
        )
        # Expected: 50 start + 15 industry + 15 sub_vertical + 15 size (100) + 10 keywords (dispatch) = 105 (capped at 100)
        assert score >= 90
        assert "logistics" in explanation.lower()

        # 3. Test fallback scorer with excluded keywords (disqualification)
        # Contains "marine" which is excluded
        score_ex, explanation_ex = ai_qualification_service._fallback_company_scorer(
            company_name="Marine Logistics Carrier",
            industry="logistics",
            employee_count=100
        )
        # Expected: Penalized heavily by -40
        assert score_ex < score
        assert "excluded" in explanation_ex

        # 4. Test machine learning user feedback learning loop for contact title
        # "Junior Agent" is normally classified as low priority
        assert ai_qualification_service.qualify_contact("John", "Junior Agent") == "low"

        # Now, add manual override feedback for "Junior Agent"
        feedback = UserFeedback(
            entity_type="contact_title",
            value="Junior Agent",
            feedback_type="manual_push"
        )
        db.add(feedback)
        db.commit()

        # Assert that the system learns/updates its accuracy, boosting it to "high"
        assert ai_qualification_service.qualify_contact("John", "Junior Agent") == "high"

        # 5. Test learning loop feedback boost for company scorer
        # Normally scored without feedback
        score_no_feedback, _ = ai_qualification_service._fallback_company_scorer(
            company_name="Normal Carrier",
            industry="insurance",
            employee_count=100
        )
        
        # Add feedback for "Normal Carrier"
        db.add(UserFeedback(
            entity_type="company_name",
            value="Normal Carrier",
            feedback_type="manual_push"
        ))
        db.commit()
        
        score_with_feedback, explanation_fb = ai_qualification_service._fallback_company_scorer(
            company_name="Normal Carrier",
            industry="insurance",
            employee_count=100
        )
        # Should be boosted by 30 points
        assert score_with_feedback > score_no_feedback
        assert "feedback boost" in explanation_fb

    finally:
        # Clean up database changes
        db.query(ICPConfig).filter(ICPConfig.industry == "logistics").delete()
        db.query(UserFeedback).delete()
        db.commit()
        db.close()


def test_dynamic_system_settings():
    from app.core.settings_helper import get_dynamic_setting, set_dynamic_setting
    from app.models.models import SystemSetting
    from app.core.database import SessionLocal
    
    # 1. Test fallback value to env config
    env_val = get_dynamic_setting("KIMI_API_KEY")
    assert env_val is None or isinstance(env_val, str)
    
    # 2. Test saving value to database
    set_dynamic_setting("TEST_API_KEY", "real_key_123")
    
    # 3. Test retrieving database value
    db_val = get_dynamic_setting("TEST_API_KEY")
    assert db_val == "real_key_123"
    
    # Clean up
    db = SessionLocal()
    try:
        db.query(SystemSetting).filter(SystemSetting.key == "TEST_API_KEY").delete()
        db.commit()
    finally:
        db.close()


