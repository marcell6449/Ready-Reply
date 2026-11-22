"""Reading WhatsApp chat exports and finding questions, answers and business details."""

from pathlib import Path

import pytest

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.search.stopwords import STOP_WORDS
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.whatsapp.analysis import ChatAnalyzer, guess_business_sender, senders_of
from readyreply.domain.whatsapp.parser import ChatMessage, parse_chat

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "whatsapp"
BUSINESS = "Soda La Esquina"


def chat(name: str) -> list[ChatMessage]:
    return parse_chat((FIXTURES / name).read_text(encoding="utf-8"))


def analyzer() -> ChatAnalyzer:
    return ChatAnalyzer(Tokenizer(STOP_WORDS))


def all_chats() -> list[list[ChatMessage]]:
    return [chat("android_soda.txt"), chat("android_soda_2.txt"), chat("ios_soda.txt")]


def test_android_export_is_read_without_system_or_media_messages() -> None:
    messages = chat("android_soda.txt")
    assert messages[0] == ChatMessage("María López", "Hola buenas")
    assert ChatMessage("María López", "¿A qué hora abren hoy?") in messages
    assert all("cifrados" not in m.text and "Multimedia" not in m.text for m in messages)


def test_multiline_message_is_joined() -> None:
    sinpe = next(m for m in chat("android_soda.txt") if m.sender == BUSINESS and "SINPE" in m.text)
    assert sinpe.text.endswith("a nombre de María Rodríguez.\nPor favor envíe el comprobante 🙏")


def test_ios_export_and_deleted_or_omitted_media() -> None:
    messages = chat("ios_soda.txt")
    assert messages[0] == ChatMessage("Ana", "Hola! cuanto cuesta el casado?")
    assert all("omitida" not in m.text and "cifrados" not in m.text for m in messages)
    assert all("eliminó" not in m.text for m in chat("android_soda_2.txt"))


def test_english_export() -> None:
    assert chat("android_english.txt")[0] == ChatMessage("John", "Hi! What time do you open?")


@pytest.mark.parametrize("text", ["", "hola", "esto no es un chat\nni de WhatsApp"])
def test_text_without_messages_is_rejected(text: str) -> None:
    with pytest.raises(InvalidInputError) as error:
        parse_chat(text)
    assert error.value.code == "whatsapp.no_messages"


def test_business_is_the_sender_present_in_every_chat() -> None:
    assert guess_business_sender(all_chats()) == BUSINESS
    assert senders_of(all_chats())[0] == BUSINESS


def test_business_in_a_single_chat_is_the_one_who_answers() -> None:
    assert guess_business_sender([chat("android_soda.txt")]) == BUSINESS


def test_repeated_questions_become_one_answer_with_the_business_reply() -> None:
    result = analyzer().analyze(all_chats(), BUSINESS)
    hours = next(a for a in result.answers if "abren" in a.question.casefold())
    assert hours.times_asked == 2
    assert hours.reply.startswith("¡Hola! Abrimos de lunes a sábado") or hours.reply.startswith(
        "Abrimos"
    )
    sinpe = next(a for a in result.answers if "sinpe" in a.question.casefold())
    assert sinpe.times_asked == 2
    assert "8888-1234" in sinpe.reply


def test_questions_never_answered_go_to_unanswered() -> None:
    result = analyzer().analyze(all_chats(), BUSINESS)
    parking = next(q for q in result.unanswered if "parqueo" in q.question)
    assert parking.times_asked == 2
    assert all("parqueo" not in a.question for a in result.answers)


def test_greetings_and_thanks_are_not_questions() -> None:
    result = analyzer().analyze(all_chats(), BUSINESS)
    asked = [a.question for a in result.answers] + [q.question for q in result.unanswered]
    assert not any(q.casefold().startswith(("hola buenas", "gracias")) for q in asked)


def test_business_details_are_detected() -> None:
    details = {d.key: d.value for d in analyzer().analyze(all_chats(), BUSINESS).details}
    assert details["sinpe"] == "8888-1234 a nombre de María Rodríguez"
    assert "6:30 a.m. a 4:00 p.m." in details["hours"]
    assert details["address"] == "100 m norte de la iglesia de San Pedro, Montes de Oca"


def test_known_values_become_placeholders_in_replies() -> None:
    result = analyzer().analyze(
        all_chats(), BUSINESS, {"sinpe": "8888-1234 a nombre de María Rodríguez"}
    )
    sinpe = next(a for a in result.answers if "sinpe" in a.question.casefold())
    assert "{sinpe}" in sinpe.reply
    assert "8888-1234" not in sinpe.reply


def test_customer_names_never_appear_in_the_result() -> None:
    result = analyzer().analyze(all_chats(), BUSINESS)
    texts = [a.question + a.reply for a in result.answers] + [q.question for q in result.unanswered]
    text = " ".join(texts + [d.value for d in result.details])
    for name in ("María López", "Ana", "7777 5555"):
        assert name not in text


def test_answers_are_sorted_by_how_often_they_were_asked() -> None:
    result = analyzer().analyze(all_chats(), BUSINESS)
    counts = [a.times_asked for a in result.answers]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.parametrize(
    ("question", "title"),
    [
        ("Buenas, a que hora abren", "A que hora abren"),
        ("Hola! cuanto cuesta el casado?", "Cuanto cuesta el casado"),
        ("Buenos días, ¿tienen envíos?", "Tienen envíos"),
        ("Y cuál es el número de SINPE?", "Cuál es el número de SINPE"),
        ("Hola buenas tardes. Hacen pasteles?", "Hacen pasteles"),
        ("Hola", "Hola"),
    ],
)
def test_titles_drop_greetings(question: str, title: str) -> None:
    from readyreply.domain.whatsapp.analysis import question_title

    assert question_title(question) == title


def test_business_message_before_any_question_is_ignored() -> None:
    messages = [
        ChatMessage(BUSINESS, "¡Bienvenido a Soda La Esquina!"),
        ChatMessage("Cliente", "¿Tienen café?"),
        ChatMessage(BUSINESS, "Sí, tenemos café chorreado."),
    ]
    (answer,) = analyzer().analyze([messages], BUSINESS).answers
    assert (answer.question, answer.reply) == ("Tienen café", "Sí, tenemos café chorreado.")


def test_short_known_values_are_not_replaced() -> None:
    from readyreply.domain.whatsapp.analysis import with_placeholders

    assert with_placeholders("Abrimos a las 8", {"hours": "8"}) == "Abrimos a las 8"
    assert with_placeholders("Tel 2222-1234", {"phone": "2222-1234"}) == "Tel {phone}"


def test_sinpe_number_without_dash_is_formatted() -> None:
    from readyreply.domain.whatsapp.details import detect_details

    (detail,) = detect_details(["Nuestro SINPE es 88881234"])
    assert (detail.key, detail.value) == ("sinpe", "8888-1234")


def test_no_senders_means_no_business() -> None:
    assert guess_business_sender([]) is None


def test_messages_keep_their_timestamp_for_fingerprints() -> None:
    from readyreply.domain.whatsapp.parser import message_fingerprint

    first, second = chat("android_soda.txt")[:2]
    assert first.stamp and first.stamp == second.stamp
    assert message_fingerprint(first) != message_fingerprint(second)
    assert len(message_fingerprint(first)) == 32
    assert "María" not in message_fingerprint(first)


def test_questions_already_seen_are_not_counted_again() -> None:
    first = analyzer().analyze(all_chats(), BUSINESS)
    seen = frozenset(first.question_fingerprints)
    again = analyzer().analyze(all_chats(), BUSINESS, skip=seen)
    assert again.answers == []
    assert again.unanswered == []
    assert again.question_fingerprints == ()


def test_new_messages_in_a_re_exported_chat_are_counted() -> None:
    first = analyzer().analyze([chat("android_soda.txt")], BUSINESS)
    longer = [
        *chat("android_soda.txt"),
        ChatMessage("Pedro", "¿Venden café molido?", "20/11/24, 8:00"),
    ]
    again = analyzer().analyze([longer], BUSINESS, skip=frozenset(first.question_fingerprints))
    assert [q.question for q in again.unanswered] == ["Venden café molido"]
