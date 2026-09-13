
import pytest
from fastapi import HTTPException
from backend.services import eta_service
from backend.schemas import RouteDistanceInput

def test_driving_units_and_waypoints(monkeypatch):
    eta_service._cache.clear()
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY','test')
    def post(url, **kwargs):
        assert kwargs['json']['origin']['location']['latLng']=={'latitude':0,'longitude':0}
        assert kwargs['json']['destination']=={'address':'Destination'}
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'routes':[{'distanceMeters':1609.344,'duration':'61s'}]}
        return Response()
    monkeypatch.setattr(eta_service.httpx,'post',post)
    result=eta_service.route((0,0),'Destination')
    assert result['distance_miles']==1
    assert result['distance_meters']==1609.344
    assert result['drive_minutes']==2
    assert result['distance_type']=='driving'

@pytest.mark.parametrize('point',[(91,0),(0,181),(float('nan'),0),(None,0)])
def test_invalid_coordinates(point):
    with pytest.raises(HTTPException):
        eta_service.waypoint(point)

def test_missing_route_is_not_zero(monkeypatch):
    eta_service._cache.clear()
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY','test')
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'routes':[]}
    monkeypatch.setattr(eta_service.httpx,'post',lambda *a,**k:Response())
    with pytest.raises(HTTPException) as error:
        eta_service.route('Origin','Destination')
    assert error.value.status_code==503

def test_route_input_rejects_missing_coordinates():
    with pytest.raises(ValueError):
        RouteDistanceInput.model_validate({'origin':{'latitude':None,'longitude':0},'destination':{'latitude':0,'longitude':0}})
