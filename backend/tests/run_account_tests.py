import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

def run():
    with tempfile.TemporaryDirectory(prefix='dashvanti-account-tests-') as directory:
        config=types.ModuleType('backend.config')
        config.settings=SimpleNamespace(database_url='sqlite:///'+str(Path(directory)/'tests.db'),jwt_secret='isolated-account-tests-only-secret-1234567890',file_root=str(Path(directory)/'files'),admin_secret='test-admin')
        sys.modules['backend.config']=config
        from backend import models, customer_account_models, account_enhancement_models, payment_models, social_models, delivery_fee_models
        from backend import models_driver_queue, models_driver_partner, models_gps, models_driver_agreement, models_order_stream, restaurant_experience_models, customer_push_models
        from backend.db import Base,engine
        from sqlalchemy import event
        @event.listens_for(engine,'connect')
        def enforce_foreign_keys(connection,record):connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(engine)
        suite=unittest.defaultTestLoader.loadTestsFromName('backend.tests.test_account_enhancements')
        result=unittest.TextTestRunner(verbosity=1).run(suite)
        engine.dispose()
        return result.wasSuccessful()

if __name__=='__main__':
    raise SystemExit(0 if run() else 1)
