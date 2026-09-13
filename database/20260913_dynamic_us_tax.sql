ALTER TABLE menu_items ADD (category VARCHAR2(80 CHAR) DEFAULT 'food' NOT NULL);
ALTER TABLE orders ADD (
  customer_zip VARCHAR2(10 CHAR),
  subtotal NUMBER(12,2) DEFAULT 0 NOT NULL,
  item_tax_total NUMBER(12,2) DEFAULT 0 NOT NULL,
  delivery_tax NUMBER(12,2) DEFAULT 0 NOT NULL,
  platform_fee NUMBER(12,2) DEFAULT 0 NOT NULL,
  platform_tax NUMBER(12,2) DEFAULT 0 NOT NULL,
  grand_total NUMBER(12,2) DEFAULT 0 NOT NULL
);
