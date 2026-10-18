# Festival Registration MVP — starter

This is a local prototype built with Python, Flask and SQLite to get the first version running quickly.

## Included
- Public event landing page
- Ticket order form
- Vendor booth reservation form
- Order references and pending-payment status
- Basic organizer dashboard and event branding customization
- Starter ticket and booth packages

## Run on Windows
1. Install Python 3.10+ from https://www.python.org/downloads/ (enable **Add Python to PATH**).
2. Extract this folder.
3. Open the folder in VS Code.
4. Open Terminal → New Terminal.
5. Run:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```

6. Open http://127.0.0.1:5000

## Important before public launch
- This is a development starter, not a production-ready ticketing/payment system.
- The organizer page currently has no login; do not expose it publicly yet.
- M-Pesa is **not connected yet**. Orders are saved as `PENDING`; this app does not take money.
- Next: create a Daraja sandbox app, add server-side STK Push, expose an HTTPS callback, verify successful callbacks, prevent duplicate receipts, and only then mark an order `PAID`.
- Add proper admin authentication, CSRF protection, input validation, inventory locking, privacy policy, backups, and production database before going live.
- Do not put Daraja secrets in frontend JavaScript or commit them to Git.
