import pytest

from src.domain.runtime.policy.handoff_request import is_explicit_handoff_request


@pytest.mark.parametrize(
    "text",
    [
        "Позови менеджера",
        "Позовите менеджера",
        "Хочу поговорить с менеджером",
        "Соедини меня с оператором",
        "Соедините меня с человеком",
        "Мне нужен живой человек",
        "Передай вопрос менеджеру",
        "Call a manager",
        "Connect me to a human",
        "I want to speak to a manager",
        "I want to speak to an operator",
        "Talk to a manager",
        "Можно менеджера?",
        "А можно позвать менеджера?",
        "Дайте оператора",
        "Соедините, пожалуйста, с человеком",
        "Хочу живого оператора",
        "Could I speak to a manager?",
        "Can you connect me with a human?",
        "Get me an operator",
    ],
)
def test_is_explicit_handoff_request_accepts_action_requests(text: str):
    assert is_explicit_handoff_request(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Как менеджер работает с обращениями?",
        "Когда подключается менеджерский контур?",
        "Что видит менеджер?",
        "Какие права есть у менеджера?",
        "Сколько человек может пользоваться системой?",
        "Поддерживается ли human-in-the-loop?",
        "Что означает human handoff?",
        "Как работает operator workflow?",
        "Есть ли manager dashboard?",
        "Чем клиентский бот отличается от менеджерского?",
        "Не зови менеджера",
        "Менеджера звать не нужно",
        "Не хочу говорить с оператором",
        "Не хочу поговорить с менеджером",
        "Я не хочу говорить с менеджером",
        "Я не хочу разговаривать с оператором",
        "Не надо звать менеджера",
        "Не нужно соединять меня с человеком",
        "Не соединяй меня с оператором",
        "Без менеджера, пожалуйста",
        "I do not want a manager",
        "I don't want to speak to a manager",
        "I do not want to talk to an operator",
        "I don't need a human",
        "Do not call a manager",
        "Don't connect me to a human",
        "Please don't connect me to a human",
        "Please don't get me an operator",
        "No need to call an operator",
    ],
)
def test_is_explicit_handoff_request_rejects_informational_mentions(text: str):
    assert is_explicit_handoff_request(text) is False
