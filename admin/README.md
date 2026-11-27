# SILONG admin console

A separate app for Admins: sign in, then handle reports on the Live map. It has its own link
(`http://localhost:5174`), shares no files with the user site (`../frontend`) and talks to the same backend.

## Run it

1. Start the backend (see the main README). It must be on `http://127.0.0.1:8000`.
2. Create the Admin account once, from the `backend` folder: `py scripts/create_admin.py`
   (or load demo data with `py scripts/seed_demo.py --db demo.db --with-demo-staff`).
3. In this folder: copy `.env.example` to `.env`, then

   ```
   npm install
   npm run dev
   ```

4. Open `http://localhost:5174` and sign in with the Admin name and password.

The backend's `CORS_ORIGINS` (in `backend/.env`) must include `http://localhost:5174`. The default does.
Restart `npm run dev` after changing `.env`.

Other commands: `npm run build` (type check and build) and `npm run lint`.

## Rules this app follows

- One role (Admin). No role label, no locked tabs, no link to the user site.
- The sign-in token is kept in `sessionStorage` of this site only and is sent only in the `Authorization` header.
- After the number of idle minutes the server reports at sign-in (30), the console signs the Admin out by itself.
- Built so far: sign in, session handling, the top bar, and the Live map (computer and phone layout).
  Places, Content, Accounts, Audit log, Blocked phones and Change password come later.
