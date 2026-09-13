from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import oracle
from backend.db import Base, engine
from backend import models

EXTRA_COLUMNS = {
    'users': [('order_sound_enabled', 'NUMBER(1)', '0')],
    'cart_items': [('special_instructions', 'VARCHAR2(1000 CHAR)', 'NULL')],
    'order_items': [('special_instructions', 'VARCHAR2(1000 CHAR)', 'NULL')],
    'addresses': [('is_default', 'NUMBER(1)', '0'), ('place_id', 'VARCHAR2(255 CHAR)', 'NULL')],
    'customers': [
        ('order_mode', 'VARCHAR2(20 CHAR)', "'delivery'"),
    ],
    'customer_locations': [
        ('address', 'VARCHAR2(500 CHAR)', "NULL"),
    ],
    'restaurants': [
        ('description', 'VARCHAR2(1000 CHAR)', "''"),
    ],
    'drivers': [
        ('vehicle_type', 'VARCHAR2(80 CHAR)', "''"),
        ('vehicle_number', 'VARCHAR2(80 CHAR)', "''"),
    ],
    'orders': [
        ('tip', 'NUMBER(12,2)', '0'),
        ('tax', 'NUMBER(12,2)', '0'),
        ('service_fee', 'NUMBER(12,2)', '0'),
        ('discount', 'NUMBER(12,2)', '0'),
        ('customer_zip', 'VARCHAR2(10 CHAR)', 'NULL'),
        ('subtotal', 'NUMBER(12,2)', '0'),
        ('item_tax_total', 'NUMBER(12,2)', '0'),
        ('delivery_tax', 'NUMBER(12,2)', '0'),
        ('platform_fee', 'NUMBER(12,2)', '0'),
        ('platform_tax', 'NUMBER(12,2)', '0'),
        ('grand_total', 'NUMBER(12,2)', '0'),
    ],
    'menu_items': [
        ('category', 'VARCHAR2(80 CHAR)', "'General'"),
    ],
}

EXTRA_TABLES = [
    models.DriverLocation.__table__,
    models.CustomerLocation.__table__,
]

def add_missing_columns():
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in EXTRA_COLUMNS.items():
            existing = {column['name'].lower() for column in inspector.get_columns(table)}
            for name, ddl_type, default in columns:
                if name.lower() in existing:
                    continue
                if engine.dialect.name == 'oracle':
                    connection.execute(text(f'ALTER TABLE {table} ADD ({name} {ddl_type} DEFAULT {default})'))
                else:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} VARCHAR DEFAULT {default}'))

if __name__ == '__main__':
    import sys
    if '--sql' in sys.argv:
        for table in Base.metadata.sorted_tables:
            print(str(CreateTable(table).compile(dialect=oracle.dialect())) + ';')
            for index in table.indexes:
                print(str(CreateIndex(index).compile(dialect=oracle.dialect())) + ';')
    else:
        Base.metadata.create_all(engine)
        for table in EXTRA_TABLES:
            table.create(engine, checkfirst=True)
        add_missing_columns()
