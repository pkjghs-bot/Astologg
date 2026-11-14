# Astrology Project

## Install Dependencies on Your Laptop

Run the following command in your terminal/command prompt to install the required libraries:

```bash
pip install fastapi uvicorn jyotishganit geopy timezonefinder pytz
```

---

### Recommended Setup (Using a Virtual Environment)

It is recommended to use a Python virtual environment to avoid conflicts:

#### 1. Create a virtual environment
```bash
python -m venv .venv
```

#### 2. Activate the virtual environment
- **Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **macOS / Linux:**
  ```bash
  source .venv/bin/activate
  ```

#### 3. Install dependencies
```bash
pip install -r requirements.txt
```
or directly:
```bash
pip install fastapi uvicorn jyotishganit geopy timezonefinder pytz
```

---

## Create the Local Calculation API

The API is saved in [`main.py`](file:///e:/COMPANY-SELF/Python%20Project/Astrology%201/main.py).

### Run the API Server

Start the local server with Uvicorn:

```bash
uvicorn main:app --reload --port 8000
```

- API Base URL: `http://localhost:8000`
- Interactive Swagger Documentation: `http://localhost:8000/docs`
- Endpoint: `POST /api/kundali`

