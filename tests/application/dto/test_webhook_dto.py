from src.application.dto.webhook_dto import WebhookAckDto


def test_webhook_ack_dto_serializes_ok_flag():
    assert WebhookAckDto().to_dict() == {"ok": True}
