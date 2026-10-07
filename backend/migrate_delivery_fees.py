from sqlalchemy import inspect
from sqlalchemy.schema import CreateColumn
from backend.db import engine, Session
from backend.models import Address
from backend.delivery_fee_models import Country, CountryDeliverySettings, DeliverySurgeRule, OrderDeliveryFeeSnapshot
from backend.delivery_fee_schemas import CountryInput, DeliverySettingsInput
from backend.services.delivery_fee_service import save_country, save_settings


def migrate():
    existing = {row['name'] for row in inspect(engine).get_columns('addresses')}
    with engine.begin() as connection:
        for name in ('country', 'state', 'city', 'latitude', 'longitude'):
            if name not in existing:
                ddl = str(CreateColumn(Address.__table__.c[name]).compile(dialect=engine.dialect))
                statement = f'ALTER TABLE addresses ADD ({ddl})' if engine.dialect.name == 'oracle' else f'ALTER TABLE addresses ADD COLUMN {ddl}'
                connection.exec_driver_sql(statement)
    for model in (Country, CountryDeliverySettings, DeliverySurgeRule, OrderDeliveryFeeSnapshot):
        model.__table__.create(engine, checkfirst=True)
    from sqlalchemy import select
    defaults = [
        ('IN', 'India', 'INR', '₹', 'km', '20', '150', '10', '499', '5', '0', [(3, 0), (5, 10), (8, 20), (12, 35), (None, 35, 5)]),
        ('US', 'United States', 'USD', '$', 'miles', '2.99', '10', '2', '35', '5', '8', [(2, 0), (5, 1.99), (8, 3.99), (12, 5.99), (None, 5.99, .5)])]
    with Session() as db:
        for code, name, currency, symbol, unit, base, small_threshold, small, free, max_distance, percent, tiers in defaults:
            if not db.scalar(select(Country.id).where(Country.country_code == code)):
                save_country(db, CountryInput(country_code=code, country_name=name, currency_code=currency, currency_symbol=symbol, distance_unit=unit,
                    minimum_service_percent=0 if code == 'IN' else 5, maximum_service_percent=5 if code == 'IN' else 15))
            if not db.scalar(select(CountryDeliverySettings.id).where(CountryDeliverySettings.country_code == code, CountryDeliverySettings.state == '', CountryDeliverySettings.city == '')):
                save_settings(db, code, DeliverySettingsInput(base_fee=base, small_order_threshold=small_threshold, small_order_fee=small,
                    free_delivery_threshold=free, free_delivery_max_distance=max_distance, service_fee_percent=percent,
                    distance_tiers=[{'up_to': tier[0], 'fee': tier[1], 'per_unit': tier[2] if len(tier) == 3 else 0} for tier in tiers]))
        db.commit()


if __name__ == '__main__':
    migrate()
    print('Delivery fee schema and national defaults installed; existing settings and orders preserved.')
