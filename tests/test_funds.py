from decimal import Decimal
from backend.schemas import FundRuleInput
from backend.services.fund_service import save_rule, delete_rule, calculate

def test_database_fee_changes_and_deletion(client):
    with client.db_factory() as db:
        save_rule(db, 'tax', FundRuleInput(method='percent', value='8.5'))
        save_rule(db, 'service_fee', FundRuleInput(method='percent', value='5', minimum='1.50'))
        save_rule(db, 'delivery_fee', FundRuleInput(value='2.99'))
        save_rule(db, 'discount', FundRuleInput(method='percent', value='10'))
        db.commit()
    with client.db_factory() as db:
        result = calculate(db, Decimal('20'), 'delivery')
        assert result['tax'] == Decimal('1.70')
        assert result['service_fee'] == Decimal('1.50')
        assert result['discount'] == Decimal('2.00')
        assert result['total'] == Decimal('24.19')
        assert calculate(db, Decimal('20'), 'pickup')['total'] == Decimal('21.20')
        delete_rule(db, 'delivery_fee')
        db.commit()
    with client.db_factory() as db:
        assert calculate(db, Decimal('20'), 'delivery')['delivery_fee'] == 0
