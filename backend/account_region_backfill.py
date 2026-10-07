from sqlalchemy import select
from backend.db import Session
from backend.models import Restaurant, CustomerLocation, User
from backend.customer_account_models import CustomerProfile
from backend.account_enhancement_models import RestaurantRegion
from backend.services.restaurant_location_service import geocode


def run():
    with Session() as db:
        count=0
        for store in db.scalars(select(Restaurant)):
            if db.get(RestaurantRegion,store.id):continue
            found=geocode(address=store.address) if store.address else None
            if not found or not found.get('city') or found.get('country')!=store.country:continue
            db.add(RestaurantRegion(restaurant_id=store.id,city=found['city'],state=found.get('state','')))
            count+=1
        db.commit()
        print('Restaurant city records populated:',count)
        customers=0
        for location in db.scalars(select(CustomerLocation)):
            user=db.get(User,location.customer_id)
            profile=db.get(CustomerProfile,location.customer_id)
            if not user or profile and profile.city:continue
            found=geocode(latlng=f'{location.latitude},{location.longitude}')
            if not found or found.get('country') not in {'IN','US'} or not found.get('city'):continue
            if not profile:profile=CustomerProfile(customer_id=user.id);db.add(profile)
            profile.city,profile.state=found['city'],found.get('state','')
            user.country=location.country=found['country']
            customers+=1
        db.commit()
        print('Current customer regions populated:',customers)


if __name__=='__main__':run()
