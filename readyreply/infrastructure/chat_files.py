"""Read WhatsApp exports: a .txt file (Android) or a .zip with _chat.txt (iPhone)."""

import io
import zipfile

from readyreply.domain.errors import InvalidInputError, PayloadTooLargeError

ZIP_SIGNATURE = b"PK\x03\x04"
MAX_FILES_IN_ZIP = 50
_ENCODINGS = ("utf-8-sig", "utf-16")


def _decode(data: bytes) -> str:
    for encoding in _ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidInputError("whatsapp.invalid_file")


def _chat_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    return [
        info
        for info in archive.infolist()
        if info.filename.lower().endswith(".txt") and not info.filename.startswith("__MACOSX")
    ][:MAX_FILES_IN_ZIP]


class WhatsAppExportReader:
    def texts(self, data: bytes, max_bytes: int) -> list[str]:
        if not data.startswith(ZIP_SIGNATURE):
            return [_decode(data)]
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                members = _chat_members(archive)
                if sum(info.file_size for info in members) > max_bytes:
                    raise PayloadTooLargeError("whatsapp.too_large", limit=max_bytes)
                return [_decode(archive.read(info)) for info in members]
        except zipfile.BadZipFile as error:
            raise InvalidInputError("whatsapp.invalid_file") from error
