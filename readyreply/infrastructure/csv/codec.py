"""CSV bytes ⇄ rows. Accepts UTF-8 with or without BOM, comma or semicolon (F10)."""

import csv
import io
from collections.abc import Sequence

from readyreply.domain.errors import InvalidInputError

_BOM_ENCODING = "utf-8-sig"
_DELIMITERS = (",", ";")


def _decode_text(data: bytes) -> str:
    try:
        text = data.decode(_BOM_ENCODING)
    except UnicodeDecodeError as error:
        raise InvalidInputError("csv.invalid_encoding") from error
    if "\x00" in text:
        raise InvalidInputError("csv.invalid_encoding")
    if not text.strip():
        raise InvalidInputError("csv.empty")
    return text


def _delimiter(text: str) -> str:
    first_line = text.splitlines()[0]
    return max(_DELIMITERS, key=first_line.count)


def _is_blank(row: dict[str | None, object]) -> bool:
    return all(not (cell.strip() if isinstance(cell, str) else cell) for cell in row.values())


class StandardCsvCodec:
    def decode(self, data: bytes) -> tuple[list[str], list[dict[str, str]]]:
        text = _decode_text(data)
        reader = csv.DictReader(
            io.StringIO(text, newline=""), delimiter=_delimiter(text), strict=True
        )
        try:
            rows = [dict(row) for row in reader if not _is_blank(row)]
        except csv.Error as error:
            raise InvalidInputError("csv.malformed") from error
        return list(reader.fieldnames or []), rows

    def encode(self, header: Sequence[str], rows: Sequence[Sequence[str]]) -> bytes:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
        return buffer.getvalue().encode(_BOM_ENCODING)
