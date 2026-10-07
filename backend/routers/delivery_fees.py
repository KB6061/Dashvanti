from fastapi import APIRouter, Depends
from backend.db import get_db
from backend.security import admin_secret
from backend.delivery_fee_schemas import CountryInput, DeliverySettingsInput, SurgeInput
from backend.delivery_fee_models import CountryDeliverySettings, DeliverySurgeRule
from backend.services import delivery_fee_service as service

router = APIRouter(prefix='/admin/delivery-fees', dependencies=[Depends(admin_secret)])


@router.get('')
def configuration(db=Depends(get_db, scope='function')):
    return service.configuration(db)


@router.put('/countries')
def country(data: CountryInput, db=Depends(get_db, scope='function')):
    return service.save_country(db, data)


@router.put('/settings/{country_code}')
def settings(country_code: str, data: DeliverySettingsInput, db=Depends(get_db, scope='function')):
    return service.save_settings(db, country_code.upper(), data)


@router.delete('/settings/{rule_id}')
def delete_settings(rule_id: int, db=Depends(get_db, scope='function')):
    return service.delete_rule(db, CountryDeliverySettings, rule_id)


@router.post('/surges/{country_code}')
def surge(country_code: str, data: SurgeInput, db=Depends(get_db, scope='function')):
    return service.save_surge(db, country_code.upper(), data)


@router.put('/surges/{country_code}/{surge_id}')
def update_surge(country_code: str, surge_id: int, data: SurgeInput, db=Depends(get_db, scope='function')):
    return service.save_surge(db, country_code.upper(), data, surge_id)


@router.delete('/surges/{rule_id}')
def delete_surge(rule_id: int, db=Depends(get_db, scope='function')):
    return service.delete_rule(db, DeliverySurgeRule, rule_id)
