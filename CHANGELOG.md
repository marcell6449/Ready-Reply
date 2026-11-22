# Changelog

All notable changes to Ready Reply are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-22

First public release.

### Added

- Registration asks for the business WhatsApp number (optional) and links it to Ready Reply right away as the business phone. A welcome screen confirms it and lists the next steps.

- Business variables (`{name}`, `{hours}`, `{address}`, `{sinpe}`, `{phone}`, `{prices}` and custom ones), filled into every answer when copying.
- Answers: create, edit, delete and duplicate, with categories and tags.
- Tolerant search: ignores accents and case, handles typos, prefixes while typing, configurable synonyms, ranked by relevance and usage.
- One-click copy, with a fallback for phones on plain HTTP over Wi-Fi. Copying is blocked with a warning when a variable is empty.
- Unanswered questions with search counts, and creating an answer from a question.
- Administrator and staff roles, Argon2id passwords, HttpOnly session cookies, CSRF protection and login throttling.
- Statistics: most copied answers and most frequent unanswered questions.
- CSV import and export (UTF-8, comma or semicolon, per-row error report, formula-injection protection).
- Automatic import: chats saved in the `Chats de WhatsApp` folder or downloaded to Downloads are read by themselves, every file and question only once, without overwriting business details already set.
- Import from WhatsApp: drop chats exported from WhatsApp Business. Ready Reply finds the most frequent customer questions, turns the business's own replies into answers, detects the SINPE number, hours and address, and lists unanswered questions. One click saves everything; everything runs on the computer.
- Optional free AI suggestions through Ollama (default `gemma3:4b`), with a copy-and-paste fallback for any AI and an OpenAI-compatible provider. A person always reviews before saving.
- Spanish (default) and English interface from one translations file.
- Phone access over the local Wi-Fi with a locally generated QR code.
- One-click start scripts for Windows (`start.bat`) and Linux/macOS (`start.sh`) with offline wheels.
