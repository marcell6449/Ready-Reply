"""Read the text file WhatsApp creates with "Export chat" (Android and iPhone, any language)."""

import re
from dataclasses import dataclass

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.text import clean_text

_NO_BREAK_SPACES = chr(0x00A0) + chr(0x202F)  # WhatsApp puts these before "a. m."
_SPACES = f"[ {_NO_BREAK_SPACES}]"
_TIME = rf"\d{{1,2}}:\d{{2}}(?::\d{{2}})?(?:{_SPACES}*[aApP]\.?{_SPACES}?[mM]\.?)?"
# Android lines look like: 12/11/24, 9:03 a. m. - Name: text
# iPhone lines look like: [12/11/24, 9:03:10 a. m.] Name: text
_MESSAGE_START = re.compile(
    rf"^\u200e?\[?\d{{1,4}}[./-]\d{{1,2}}[./-]\d{{1,4}},?{_SPACES}+{_TIME}\]?{_SPACES}*(?:-{_SPACES})?(?P<rest>.*)$"
)
_SENDER = re.compile(r"^(?P<sender>[^:]{1,80}?):\s(?P<text>.*)$", re.S)
_SKIPPED_TEXTS = (
    "<multimedia omitido>",
    "<media omitted>",
    "imagen omitida",
    "image omitted",
    "video omitido",
    "video omitted",
    "audio omitido",
    "audio omitted",
    "sticker omitido",
    "sticker omitted",
    "documento omitido",
    "document omitted",
    "se eliminó este mensaje",
    "eliminaste este mensaje",
    "this message was deleted",
    "you deleted this message",
    "null",
)
_ENCRYPTION_NOTICE = ("cifrados de extremo a extremo", "end-to-end encrypted")


@dataclass(frozen=True, slots=True)
class ChatMessage:
    sender: str
    text: str


_INVISIBLE = " \t\n\u200e\u200f"


def _is_noise(text: str) -> bool:
    lowered = text.casefold().strip(_INVISIBLE)
    return not lowered or lowered in _SKIPPED_TEXTS or any(n in lowered for n in _ENCRYPTION_NOTICE)


def _entries(lines: list[str]) -> list[str]:
    """Group physical lines into messages: a line without a date continues the previous one."""
    entries: list[str] = []
    for line in lines:
        match = _MESSAGE_START.match(line)
        if match:
            entries.append(match.group("rest"))
        elif entries:
            entries[-1] += "\n" + line
    return entries


def parse_chat(text: str) -> list[ChatMessage]:
    messages = []
    for entry in _entries(clean_text(text).splitlines()):
        found = _SENDER.match(entry)
        if found and not _is_noise(found.group("text")):
            sender, body = (found.group(name).strip(_INVISIBLE) for name in ("sender", "text"))
            messages.append(ChatMessage(sender, body))
    if not messages:
        raise InvalidInputError("whatsapp.no_messages")
    return messages
