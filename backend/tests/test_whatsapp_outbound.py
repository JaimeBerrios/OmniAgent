from app.models import WhatsAppOutboundDelivery


def test_outbound_delivery_table():
    table = WhatsAppOutboundDelivery.__table__

    assert table.name == "whatsapp_outbound_deliveries"
    assert {"claim_token", "claimed_at"}.issubset(table.columns.keys())


def test_outbound_delivery_required_columns():
    table = WhatsAppOutboundDelivery.__table__

    required = {
        "tenant_id",
        "message_id",
        "recipient_phone",
        "status",
        "attempts",
    }

    assert required.issubset(set(table.columns.keys()))


def test_outbound_delivery_default_status():
    table = WhatsAppOutboundDelivery.__table__

    assert table.columns["status"].server_default.arg == "pending"
