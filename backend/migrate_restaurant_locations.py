from sqlalchemy import text, select
from backend.db import engine, Session
from backend.models import Restaurant, CustomerLocation
from backend.services.restaurant_location_service import geocode, configure_restaurant

def main():
    with engine.begin() as connection:
        for table,column,kind in [('restaurants','country','VARCHAR(2)'),('restaurants','latitude','DOUBLE PRECISION'),('restaurants','longitude','DOUBLE PRECISION'),('customer_locations','country','VARCHAR(2)')]:
            connection.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {kind}'))
    with Session() as db:
        for row in db.scalars(select(Restaurant)):
            configure_restaurant(row,{})
            print('Restaurant',row.id,row.country,'location saved' if row.latitude is not None and row.longitude is not None else 'needs location')
        for row in db.scalars(select(CustomerLocation).where(CustomerLocation.country.is_(None))):
            found=geocode(latlng=f'{row.latitude},{row.longitude}')
            if found:row.country=found['country']
        db.commit()

if __name__=='__main__':main()
