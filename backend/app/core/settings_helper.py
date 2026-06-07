import logging
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.models import SystemSetting

logger = logging.getLogger(__name__)

def get_dynamic_setting(key: str) -> str | None:
    """
    Retrieves the value of a configuration setting from the database,
    falling back to settings (.env) if not found or empty.
    """
    db = SessionLocal()
    try:
        db_val = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if db_val and db_val.value is not None and db_val.value.strip() != "":
            return db_val.value
    except Exception as e:
        logger.error(f"Error querying dynamic setting {key}: {str(e)}")
    finally:
        db.close()
    
    # Fallback to env setting
    val = getattr(settings, key, None)
    return val

def set_dynamic_setting(key: str, value: str | None):
    """
    Saves a configuration setting to the database.
    """
    db = SessionLocal()
    try:
        db_val = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if db_val:
            db_val.value = value
        else:
            db_val = SystemSetting(key=key, value=value)
            db.add(db_val)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving dynamic setting {key}: {str(e)}")
        raise e
    finally:
        db.close()
