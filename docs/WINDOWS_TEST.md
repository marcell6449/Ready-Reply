# Ready Reply — owner test checklist (Windows, WhatsApp, Ollama)

These checks cannot run in the Linux build environment. Tick each one before publishing.
Expected total time: about 15 minutes (plus the Ollama download, if you test it).

## A. Install on Windows (P7, F11-04, F11-05)

| # | Step | Expected | OK? |
|---|---|---|---|
| A1 | Copy `ready-reply-v1.0.0.zip` to a Windows 10/11 PC. Right-click → **Extract All** into `Documents\Ready Reply`. | A folder `ready-reply-v1.0.0` with `start.bat` inside. | ☐ |
| A2 | Double-click `start.bat`. | A black window says "Installing Ready Reply…". After about a minute, the browser opens on the "Welcome to Ready Reply" setup page. | ☐ |
| A3 | If Windows Defender firewall asks, choose **Allow** on private networks. | No error. | ☐ |
| A4 | Create the administrator. | The search screen appears. | ☐ |
| A5 | Close the black window. Double-click `start.bat` again. | It starts in a few seconds, with no "Installing" step. The data is still there. | ☐ |
| A6 | *(Optional, a PC without Python)* Double-click `start.bat`. | It offers to install Python with winget, or opens the Python download page with instructions. | ☐ |

## B. Use it (P1, P2, P3)

| # | Step | Expected | OK? |
|---|---|---|---|
| B1 | Export 3–5 chats from your WhatsApp Business (**⋮ → Más → Exportar chat → Sin archivos**), copy them to the PC, open **Importar** and drop them all. Tap **Guardar todo**. | Your business is selected, your answers, unanswered questions and SINPE/hours/address appear; after saving they are in **Respuestas**, **Sin respuesta** and **Mi negocio**. | ☐ |
| B1b | Export another chat and save it into the `Chats de WhatsApp` folder inside the program folder (or download it to Descargas). Keep **Importar** open. | Within about 10 seconds a message says a new chat was imported, and it appears in the history. | ☐ |
| B2 | Type a question a customer often asks, with a typo (for example `a que ora abren`). | The answer imported from your chats is the first result. | ☐ |
| B3 | Click **Copiar**, open WhatsApp Web and paste into a chat. | The text pastes exactly, with emojis, line breaks and *bold* as in the answer. | ☐ |
| B4 | **Mi negocio**: change the opening hours and save. Search `horario` again and copy. | The new hours appear. | ☐ |

## C. Phone on the same Wi-Fi (P3, F4-06)

| # | Step | Expected | OK? |
|---|---|---|---|
| C1 | **Abrir en el celular**: scan the QR code with your phone. | The login page opens on the phone. | ☐ |
| C2 | Sign in, search `sinpe`, tap **Copiar**, paste into WhatsApp Business. | The SINPE number pastes exactly. | ☐ |
| C3 | Search `tienen parqueo`, wait 2 seconds. On the PC, open **Sin respuesta**. | "tienen parqueo" is listed. | ☐ |

## D. Optional AI with Ollama (P5)

| # | Step | Expected | OK? |
|---|---|---|---|
| D1 | Install Ollama from ollama.com. In a terminal: `ollama pull gemma3:4b`. | The model downloads (about 3.3 GB). | ☐ |
| D2 | In **Sin respuesta**, click **Sugerir con IA** on a question. | After 10–40 seconds, a Spanish draft appears in an editable box. Nothing is saved yet. | ☐ |
| D3 | Edit the draft, click **Revisar y guardar como respuesta**, then **Guardar**. | The answer is saved and the question disappears from the list. | ☐ |
| D4 | Close Ollama (system tray → Quit) and click **Sugerir con IA** again. | A message says the local AI is not available and shows a text to copy into any AI. | ☐ |

## E. Backup

| # | Step | Expected | OK? |
|---|---|---|---|
| E1 | Close the black window. Copy the `data` folder somewhere else. | The copy contains `readyreply.db`. | ☐ |

If any step fails, write down the step number and what you saw. A screenshot helps.
