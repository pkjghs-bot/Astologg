@echo off
echo Starting Local Vedic Kundali API...
uvicorn main:app --reload --port 8000
pause
