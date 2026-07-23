# AutoMCQ

## extension/

Chrome/Firefox browser extension for automating MCQ quiz selection.

Load it unpacked in developer mode:
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** and point to the `extension/` folder

## backend/

FastAPI backend server providing the credit system and device-linking API.

```bash
cd backend/
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server starts on `http://0.0.0.0:8000`.
