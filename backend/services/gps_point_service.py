from uuid import uuid5, NAMESPACE_URL
from datetime import timezone
from sqlalchemy import select
from geographiclib.geodesic import Geodesic
from backend.models_gps import EssentialGPSPoint

def store(db,data,kind,event_id):
    if not data or not data.get('order_id'):return False
    if db.scalar(select(EssentialGPSPoint.id).where(EssentialGPSPoint.event_id==event_id)):return False
    db.add(EssentialGPSPoint(event_id=event_id,order_id=data['order_id'],driver_id=data['driver_id'],kind=kind,latitude=data['latitude'],longitude=data['longitude'],heading=data.get('heading')))
    return True

def milestone(db,order,status):
    if status not in {'PICKED_UP','DELIVERED','ON_THE_WAY_TO_RESTAURANT','ON_THE_WAY_TO_CUSTOMER'} or not order.driver_id:return
    from backend.gps_config import ENABLED
    from backend.services.redis_geo_service import live
    if not ENABLED:return
    data=live(order.driver_id)
    if not data:return
    data={**data,'order_id':order.id}
    kind={'PICKED_UP':'PICKUP','DELIVERED':'DROP_OFF'}.get(status,'ROUTE_START')
    store(db,data,kind,str(uuid5(NAMESPACE_URL,f'dashvanti:{order.id}:{status}')))

def route_point(db,data):
    if not data.get('order_id'):return
    last=db.scalar(select(EssentialGPSPoint).where(EssentialGPSPoint.order_id==data['order_id']).order_by(EssentialGPSPoint.id.desc()).limit(1))
    if last:
        elapsed=data['timestamp']/1000-last.recorded_at.replace(tzinfo=timezone.utc).timestamp()
        distance=Geodesic.WGS84.Inverse(last.latitude,last.longitude,data['latitude'],data['longitude'])['s12']
        if elapsed<120 or distance<1000:return
    store(db,data,'ROUTE_KEY',data['event_id'])
