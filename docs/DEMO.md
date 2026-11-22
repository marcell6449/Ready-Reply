# Ready Reply — 2-minute demo script

For the pitch video and the live demo. Use a phone at 360 px (or a real phone on the same
Wi-Fi) next to a laptop. Start from a fresh install.

**Before you start:** run `start.bat` and create the admin with the business WhatsApp number.
Have 3–5 chats exported from WhatsApp Business on the laptop (for the rehearsal you can use
`tests/fixtures/whatsapp/*.txt`). Open **Open on phone** and scan the QR with the phone. Sign in
on the phone.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:15 | WhatsApp Web with three messages: "a q hora abren?", "numero de simpe", "hacen express?" | "Every day, a soda in San José answers these same questions by hand. Staff scroll old chats or type from memory, and sometimes give the wrong number." |
| 0:15–0:30 | On the laptop, **Importar**: drop the exported chats. The preview shows the answers, unanswered questions and SINPE/hours/address. Tap **Guardar todo**. | "Ready Reply reads the chats you already have and builds your answers from your own replies. One click, nothing typed." |
| 0:30–0:40 | On the phone, type `a que ora abren` (with the typo). The answer appears first. Tap **Copiar** and paste into WhatsApp. | "Type a few letters, even with typos and without accents. One tap copies the answer. Two seconds." |
| 0:40–0:50 | Type `simpe`. The SINPE answer shows the real number. Copy and paste. | "The SINPE number, hours and prices are saved once. Every answer uses them." |
| 0:50–1:05 | On the laptop, **My business**: change the hours to "lunes a domingo". On the phone, search `horario` again. | "If the hours change, change them in one place, and every answer is up to date." |
| 1:05–1:25 | On the phone, search `tienen parqueo`. "No answer" appears. On the laptop, open **Unanswered**: *tienen parqueo* is listed. | "When the team cannot find an answer, Ready Reply saves the question. The owner sees exactly which answers are missing." |
| 1:25–1:45 | Click **Suggest with AI**, edit the draft, save. Search `parqueo` on the phone. | "Free, optional AI suggests the reply. It runs on this computer, and a person always reviews it before saving." |
| 1:45–2:00 | **Statistics**, then the README screenshots. | "Roles for owner and staff, stats, CSV import. It installs on Windows with a double click, needs no WhatsApp API, and customer data never leaves the business. Ready Reply." |

**Backup plan:** if Ollama is not installed on the demo laptop, **Suggest with AI** shows
the copy-and-paste prompt. Copy it into any AI chat and paste the reply back. The message
is the same: AI suggests, a human decides.
