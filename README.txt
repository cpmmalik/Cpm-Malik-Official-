CPM MALIK WEBSITE - Render deployment

1. Extract ZIP and upload the folder to a NEW GitHub repository.
2. Render -> New -> Web Service -> connect that repository.
3. Build: pip install -r requirements.txt
   Start: uvicorn main:app --host 0.0.0.0 --port $PORT
4. Add environment variables:
   ADMIN_USERNAME = choose your admin username
   ADMIN_PASSWORD = choose a strong password (keep private)
   SESSION_SECRET = long random secret
5. Deploy. Open /register to create customer accounts.
6. Admin and customer use the SAME /login page. Admin credentials are the values above.
7. JazzCash details shown on payment page: 03279023349 / Asad Abbas.
8. Admin reviews screenshot in /admin and approves/rejects it.

IMPORTANT HONEST STATUS:
- Login/register, role routing, subscription plans, JazzCash proof upload,
  manual approval, order queue, admin controls and notifications are implemented.
- Actual CPM game API execution is NOT connected yet. The uploaded bot has FK blank
  and its service logic is coupled to Telegram handlers. This website safely queues
  orders for admin processing; do not mark an order complete until the actual API
  integration is added and tested.
- Do NOT upload bot(2).py as a second running Telegram bot. This web app is separate
  and will not change or stop the existing bot.
- Render free instances may sleep. Use persistent disk or PostgreSQL before production;
  this starter uses local SQLite and local uploads.
