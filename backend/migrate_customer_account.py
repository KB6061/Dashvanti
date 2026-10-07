import inspect
from backend.db import Base, engine
from backend import customer_account_models as models

def run():
    tables=[value.__table__ for _,value in inspect.getmembers(models,inspect.isclass) if value.__module__==models.__name__ and hasattr(value,'__table__')]
    Base.metadata.create_all(engine,tables=tables)
    print('Customer account tables ready:',len(tables))

if __name__=='__main__':run()
