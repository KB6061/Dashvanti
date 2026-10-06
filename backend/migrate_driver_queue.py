from backend.db import engine
from backend import models
from backend.models_driver_queue import DriverUpcomingOrder

if __name__=='__main__':
    DriverUpcomingOrder.__table__.create(engine,checkfirst=True)
    print('Driver upcoming-order queue table ready')
