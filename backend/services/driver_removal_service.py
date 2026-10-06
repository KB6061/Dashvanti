import logging
from pathlib import Path
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models_driver_partner import DriverPartner, DriverDocument, DriverVerification, DriverDeposit, DriverWallet, DriverEarning, DriverWithdrawal, DriverWithdrawalAllocation, DriverIncident, DriverNominee, DriverInsurance, DriverInsuranceClaim, DriverOffer, DriverPartnerNotice, DriverPushDevice

logger = logging.getLogger(__name__)


def remove_partner_records(db, driver_id):
    paths = list(db.scalars(select(DriverDocument.encrypted_path).where(DriverDocument.driver_id == driver_id)))
    withdrawal_ids = select(DriverWithdrawal.id).where(DriverWithdrawal.driver_id == driver_id)
    db.execute(delete(DriverWithdrawalAllocation).where(DriverWithdrawalAllocation.withdrawal_id.in_(withdrawal_ids)))
    for model in (DriverInsuranceClaim, DriverDocument, DriverVerification, DriverDeposit, DriverWallet, DriverEarning,
                  DriverWithdrawal, DriverIncident, DriverNominee, DriverInsurance, DriverOffer, DriverPartnerNotice, DriverPushDevice, DriverPartner):
        db.execute(delete(model).where(model.driver_id == driver_id))
    db.execute(update(DriverVerification).where(DriverVerification.reviewer_id == driver_id).values(reviewer_id=None))
    db.info.setdefault('removed_drivers', []).append((driver_id, paths))


@event.listens_for(Session, 'after_rollback')
def discard_cleanup(db):
    db.info.pop('removed_drivers', None)


@event.listens_for(Session, 'after_commit')
def cleanup_after_commit(db):
    for driver_id, paths in db.info.pop('removed_drivers', []):
        try:
            from backend.services.redis_geo_service import remove
            remove(driver_id)
        except Exception:
            logger.exception('Could not clear live GPS for deleted driver %s', driver_id)
        parent = (Path(settings.file_root)/'driver-private'/str(driver_id)).resolve()
        for filename in paths:
            path = Path(filename).resolve()
            if path.parent != parent:
                logger.warning('Skipped document outside deleted driver directory: %s', driver_id)
                continue
            try: path.unlink(missing_ok=True)
            except OSError: logger.exception('Could not remove document for deleted driver %s', driver_id)
