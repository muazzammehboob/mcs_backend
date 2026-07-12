# Multidimensional AI Chatbox

This repository contains the backend and frontend for the Multidimensional AI Chatbox application.

## Multi-Provider Support

This application supports Bring Your Own Key (BYOK) for both Google AI Studio (Gemini) and Fireworks AI. API keys are strictly kept on the client-side (`localStorage`) and are only sent to the backend during the lifecycle of an LLM request. They are never stored server-side or logged.

### How to use Google AI Studio (Gemini)

1. Obtain a Gemini API Key from Google AI Studio: [https://aistudio.google.com/](https://aistudio.google.com/)
2. Open the application, click on Settings.
3. Select "Google AI Studio (Gemini)" under LLM Provider.
4. Enter your API key. 
5. Start chatting!

### How to use Fireworks AI

1. Obtain a Fireworks API Key: [https://fireworks.ai/](https://fireworks.ai/)
2. Open the application, click on Settings.
3. Select "Fireworks AI" under LLM Provider.
4. Enter your API key.
5. In the Model field, enter a Fireworks-compatible model ID (e.g., `accounts/fireworks/models/llama-v3p1-8b-instruct`).
6. Start chatting!

## Setup Instructions

### Backend (FastAPI)

1. Navigate to the backend directory (`backend for 1st`).
2. Install dependencies via poetry/pip. It requires `fastapi`, `openai`, `httpx`, etc. If using standard pip, run: `pip install -e .` or install from `pyproject.toml`.
3. Start the server: `uvicorn app.main:app --reload`
4. The server runs on `http://localhost:8000`.

### Frontend (Next.js)

1. Navigate to the frontend directory (`mcs-frontend`).
2. Install dependencies: `npm install`
3. Run the development server: `npm run dev`
4. Access the web app at `http://localhost:3000`.
