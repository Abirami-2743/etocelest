# Run ÉTOCELEST (Windows PowerShell)

## 0. MongoDB (choose one)
- Atlas free cluster (no install): https://www.mongodb.com/atlas -> create cluster, add DB user,
  allow your IP, copy the connection string (mongodb+srv://...) for MONGODB_URI below.
- Or Docker:  docker run -d --name etocelest-mongo -p 27017:27017 mongo:7
- Or install MongoDB Community Server (default URI mongodb://localhost:27017 works).

## 1. Backend (Python 3.13 recommended)
cd etocelest-backend
py -3.13 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
notepad .env          # set GROQ_API_KEY=... and MONGODB_URI=...
uvicorn app.main:app_factory --factory --port 8000
# check: http://localhost:8000/api/health  ->  "status":"ok","database":"ok"

## 2. Frontend (Node 20+), in a second terminal
cd etocelest-frontend
npm install
copy .env.example .env
npm run dev
# open http://localhost:5173
