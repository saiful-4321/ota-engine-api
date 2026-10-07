import datetime
from app.models.otadb.SupplierApiToken import SupplierApiToken
from app.helpers.common import get_ota_db_session, write_log


class SupplierTokenService:
    @staticmethod
    def get_token_from_db(supplier_id: int, token_key: str) -> str:
        """
        Retrieves a valid token from the database.
        Returns the token string if valid, else None.
        """
        db = next(get_ota_db_session())
        try:
            token_record = db.query(SupplierApiToken).filter(
                SupplierApiToken.supplier_id == supplier_id,
                SupplierApiToken.token_key == token_key
            ).first()

            if token_record and token_record.expires_at:
                now = datetime.datetime.utcnow()
                # Use a safety buffer of 60 seconds
                if token_record.expires_at > now + datetime.timedelta(seconds=60):
                    return token_record.access_token
        except Exception as e:
            write_log(f"Failed to retrieve supplier token from DB: {str(e)}", source="supplier_token_service", type="warning")
        finally:
            db.close()
            
        return None

    @staticmethod
    def save_token_to_db(supplier_id: int, token_key: str, access_token: str, expires_in_seconds: int) -> None:
        """
        Saves or updates the API token in the database.
        """
        db = next(get_ota_db_session())
        try:
            now = datetime.datetime.utcnow()
            expires_at = now + datetime.timedelta(seconds=expires_in_seconds)

            token_record = db.query(SupplierApiToken).filter(
                SupplierApiToken.supplier_id == supplier_id,
                SupplierApiToken.token_key == token_key
            ).first()

            if token_record:
                token_record.access_token = access_token
                token_record.expires_at = expires_at
                token_record.updated_at = now
            else:
                new_token = SupplierApiToken(
                    supplier_id=supplier_id,
                    token_key=token_key,
                    access_token=access_token,
                    expires_at=expires_at,
                    created_at=now,
                    updated_at=now
                )
                db.add(new_token)
            
            db.commit()
        except Exception as e:
            db.rollback()
            write_log(f"Failed to save supplier token to DB: {str(e)}", source="supplier_token_service", type="error")
        finally:
            db.close()

