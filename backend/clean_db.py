import os
import sys

# Add backend app folder to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.models.models import Company, Contact, SyncLog

def clean():
    db = SessionLocal()
    try:
        # Delete Target Claims Automation test records
        co = db.query(Company).filter(Company.domain == "targetinsurancemga.com").first()
        if co:
            print(f"Deleting test company: {co.name}")
            db.delete(co)
            
        # Delete Banyanrisk record so user can enter it completely fresh
        co_banyan = db.query(Company).filter(Company.domain == "banyanrisk.com").first()
        if co_banyan:
            print(f"Deleting company record: {co_banyan.name}")
            db.delete(co_banyan)
            
        co_rps = db.query(Company).filter(Company.domain == "riskplacementservicesinc.com").first()
        if co_rps:
            print(f"Deleting company record: {co_rps.name}")
            db.delete(co_rps)
            
        db.commit()
        print("Database cleaned successfully!")
    except Exception as e:
        print(f"Error cleaning database: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clean()
