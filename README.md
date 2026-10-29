# Aravola auth backend

Node.js backend for the React sign-up flow:

1. The React form collects email, password and password confirmation.
2. The backend sends a 6-digit OTP to that email.
3. The user verifies the OTP.
4. The backend saves the password and returns a session token.

The password stays in the React app until the email is verified. The backend only receives it at the final `create-password` call.

The React app is separate. The backend returns the frontend page URLs after each successful step.

## Files

```text
src/server.js       Environment config, Express app, all routes, rate limits, startup
src/authService.js  Validation, password rules, OTP/token cryptography, all auth logic
src/db.js           SQLite connection and database tables
src/mailer.js       SMTP/OAuth2 connection and the OTP email content
tests/auth.test.js  API tests using a fake mailer and in-memory database
docs/API.md         API reference and React integration guide
postman/aravola-auth.postman_collection.json  Postman CLI collection for the full flow
.env.example        Copy this to .env and fill in real values
README.md           Setup, email delivery and handover notes
package.json        Scripts and dependencies
```

Generated and not committed:

```text
.env           Real secrets (SMTP credentials and OTP pepper)
node_modules/  Installed packages
data/auth.db   Local SQLite database, created on first start
```

## Quick start

Requirements: Node.js 20.10 or newer.

```powershell
npm install
Copy-Item .env.example .env
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Paste the generated value into `OTP_PEPPER` in `.env`, then configure:

- `SMTP_AUTH_TYPE` — `password` for Brevo/Resend/SendGrid, or `oauth2` for Gmail
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER` and either `SMTP_PASS` or the `SMTP_OAUTH_*` values
- `MAIL_FROM` — a sender address verified by that provider
- `CORS_ORIGINS` — the React origin, for example `http://localhost:5173`
- `FRONTEND_OTP_VERIFY_URL` — the React OTP page
- `FRONTEND_CREATE_PASSWORD_URL` — optional; only needed if your React app uses a separate password page

Start the API:

```powershell
npm run dev
```

Health check: `GET http://localhost:3000/api/health`

The SQLite database is created automatically.

## How the code fits together

```text
React request
    ↓
src/server.js           routes, CORS, rate limits, JSON responses
    ↓
src/authService.js      validation, OTP/password/session logic
    ↓
src/db.js               storage
src/mailer.js           SMTP and OTP email
```

The main signup methods are in `src/authService.js`:

- `requestSignupOtp()`
- `verifySignupOtp()`
- `createPassword()`

Login and session methods are directly below them.

## API

All endpoints are under `/api`:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/request-otp` | Send a signup OTP |
| POST | `/api/auth/verify-otp` | Verify OTP and get a one-time verification token |
| POST | `/api/auth/create-password` | Save the password and receive a session |
| POST | `/api/auth/login` | Sign in with email and password |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/logout` | Revoke current session |
| GET | `/api/health` | Health check |

Request bodies, responses, error codes, password rules and React examples are in **[docs/API.md](docs/API.md)**.

Important frontend detail: the backend does not navigate the browser.

1. The signup page collects email, password and confirmation, then calls `request-otp`.
2. The OTP page calls `verify-otp`, keeps the returned `verificationToken`, then immediately calls `create-password` with the password held in React state.
3. The `create-password` response contains the `sessionToken`.

Use `request-otp.data.redirectTo` to open the OTP page. The `redirectTo` from `verify-otp` is only for the optional separate password page. See **[docs/API.md](docs/API.md)** for the full React example.

## Passwords

A password must:

- be 8–64 characters
- contain at least one uppercase letter (`A-Z`)
- contain at least one number (`0-9`)
- contain at least one special character
- contain no whitespace
- match the confirmation field

These rules are enforced in `src/authService.js`. The React form should enforce the same rules for a better user experience.

## Email delivery and spam

**No backend can guarantee inbox delivery.** The recipient's email provider decides. This code avoids common spam triggers: short transactional messages, plain-text and HTML versions, no images, no tracking pixels and no shortened links.

For the best chance of inbox delivery:

1. Use a transactional provider such as Brevo, Resend, SendGrid, Mailgun or Amazon SES.
2. Verify a domain you own with that provider.
3. Send from an address on that domain, such as `no-reply@auth.yourdomain.com`.
4. Add the provider's SPF and DKIM DNS records.
5. Publish a DMARC record.
6. Set a monitored `MAIL_REPLY_TO`.

Example records — use the exact values from your provider:

```text
yourdomain.com. TXT "v=spf1 include:provider-spf.example ~all"
_dmarc.yourdomain.com. TXT "v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com"
```

Gmail, Yahoo and Microsoft users can all receive the OTP; the recipient address is not the issue. The sender configuration matters.

### Fastest test: Resend test mode

For a quick API test with no domain, no App Password and no Google Cloud setup:

1. Create a free [Resend](https://resend.com/) account using the address that will receive the OTP.
2. In the Resend dashboard, open **API Keys** and create a key with **Sending access**.
3. Put the key in `.env` and use these settings:

```dotenv
SMTP_AUTH_TYPE=password
SMTP_HOST=smtp.resend.com
SMTP_PORT=465
SMTP_SECURE=true
SMTP_REQUIRE_TLS=false
SMTP_USER=resend
SMTP_PASS=re_your_api_key
MAIL_FROM="Aravola <onboarding@resend.dev>"
MAIL_REPLY_TO=your-resend-account-email@gmail.com
```

Send the OTP to the **same address that owns the Resend account**. Resend's shared `onboarding@resend.dev` sender only delivers to that address. For real users, verify a domain at Resend and change `MAIL_FROM` to an address on that domain.

### Send to any recipient without a domain: Brevo

If you need to send OTPs to arbitrary Gmail, Yahoo or Outlook addresses before you own a domain, use Brevo with a verified sender email:

```dotenv
SMTP_AUTH_TYPE=password
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_REQUIRE_TLS=true
SMTP_USER=your-brevo-smtp-login
SMTP_PASS=your-brevo-smtp-key
MAIL_FROM="Aravola <your-verified-sender@gmail.com>"
```

Copy the SMTP login and SMTP key from **Brevo → SMTP & API → SMTP**. Do not confuse the SMTP key with an API key.

This works today, but it is **not production-grade**. Free sender domains such as `gmail.com` cannot be authenticated with SPF/DKIM/DMARC, so Gmail, Yahoo and Microsoft may filter the message or Brevo may rewrite the sender address. For production, add a domain to Brevo, authenticate it, and change `MAIL_FROM` to an address on that domain.

### Switching to the company sender later

All email settings live in `.env`; no backend code changes are needed.

**Option A — keep Brevo (recommended):**

1. Add the company domain in Brevo and authenticate it with the DNS records Brevo provides.
2. Verify the company sender address.
3. Change only these values:

```dotenv
MAIL_FROM="Company Name <no-reply@company.com>"
MAIL_REPLY_TO=support@company.com
```

Keep `SMTP_HOST`, `SMTP_USER` and `SMTP_PASS` unchanged. The SMTP key is a Brevo credential, not the sender email password.

**Option B — use the company's own SMTP server:**

Ask the company IT team for the SMTP host, port, encryption, username and app password, then change:

```dotenv
SMTP_HOST=mail.company.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_REQUIRE_TLS=true
SMTP_USER=no-reply@company.com
SMTP_PASS=the-company-smtp-password
MAIL_FROM="Company Name <no-reply@company.com>"
MAIL_REPLY_TO=support@company.com
```

Many Microsoft 365 tenants disable SMTP AUTH, and Google Workspace may require an App Password or OAuth2. The company domain must still have SPF, DKIM and DMARC for reliable inbox delivery.

### Gmail OAuth2 (no App Password)

This backend supports Gmail OAuth2 for accounts where Google App Passwords are unavailable. The complete `.env` looks like this:

```dotenv
SMTP_AUTH_TYPE=oauth2
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_REQUIRE_TLS=true
SMTP_USER=you@gmail.com
SMTP_OAUTH_CLIENT_ID=...
SMTP_OAUTH_CLIENT_SECRET=...
SMTP_OAUTH_REFRESH_TOKEN=...
MAIL_FROM="Aravola <you@gmail.com>"
MAIL_REPLY_TO=you@gmail.com
```

Create the credentials:

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Enable **Gmail API** under **APIs & Services → Library**.
3. Configure the OAuth consent screen:
   - User type: **External** for a personal Gmail account.
   - Add your Gmail address as a **test user**.
   - Add the scope `https://mail.google.com/` (required by Gmail SMTP OAuth2).
4. Create an OAuth client:
   - **APIs & Services → Credentials → Create credentials → OAuth client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `https://developers.google.com/oauthplayground`
   - Copy the client ID and client secret.
5. Get a refresh token:
   - Open <https://developers.google.com/oauthplayground>.
   - Open the settings gear, enable **Use your own OAuth credentials**, and paste the client ID and secret.
   - In Step 1, enter `https://mail.google.com/`, click **Authorize APIs**, and approve with the Gmail account.
   - In Step 2, click **Exchange authorization code for tokens** and copy the refresh token.
6. Put the client ID, client secret and refresh token in `.env`.

`https://mail.google.com/` is a restricted scope with full mailbox access. Use a dedicated Gmail account, keep `.env` private, and revoke access at <https://myaccount.google.com/permissions> if it leaks.

Google issues refresh tokens that expire after **7 days** while the OAuth app is in **Testing**. To avoid re-authorizing every week, publish the app in **Google Auth Platform → Audience → Publish app**. For a personal integration, you can click through the unverified-app warning; a public multi-user app needs Google verification. If your Google account or Workspace administrator blocks OAuth apps, use Brevo instead.

Personal Gmail has daily sending limits and is more likely to be filtered than a dedicated sending domain. Microsoft SMTP basic authentication is usually disabled. Use a transactional provider on a domain you own for production.

Common SMTP settings:

| Provider | Host | Port | Secure | Username | Password |
| --- | --- | --- | --- | --- | --- |
| Brevo | `smtp-relay.brevo.com` | 587 | false | account email | SMTP key |
| Resend | `smtp.resend.com` | 465 | true | `resend` | API key |
| SendGrid | `smtp.sendgrid.net` | 587 | false | `apikey` | API key |
| Gmail OAuth2 | `smtp.gmail.com` | 587 | false | Gmail address | OAuth2 client ID, secret and refresh token |

Check the received message headers for `SPF: PASS`, `DKIM: PASS` and `DMARC: PASS`. You can also test with <https://www.mail-tester.com/>.

## Security notes

- OTPs, verification tokens and session tokens are stored as hashes only.
- Passwords are hashed with bcrypt.
- OTPs expire, have limited attempts and cannot be resent instantly.
- Rate limits protect OTP, password and login endpoints.
- CORS only allows origins listed in `CORS_ORIGINS`.
- Never commit `.env`.
- Treat SMTP keys and OAuth2 refresh tokens like passwords; revoke them if leaked.
- Use HTTPS in production.
- Use a strong, unique `OTP_PEPPER`.
- The rate limiter is in memory. Use a shared Redis store for multiple server instances.
- SQLite is used for simple deployment. Move to PostgreSQL when you need multiple app instances.
- Password reset and email-change flows are not included yet.

## Where to change things

| Change | File |
| --- | --- |
| Email credentials (SMTP/OAuth2), frontend links, CORS | `.env` |
| OTP email wording or design | `src/mailer.js` |
| Password requirements | `src/authService.js` (`passwordPolicyErrors`) |
| API routes, configuration, rate limits | `src/server.js` |
| Database tables | `src/db.js` |
| Tests | `tests/auth.test.js` |

## Tests

```powershell
npm test
```

Current suite: 11 tests covering signup, OTP limits, password rules, login/session, CORS and errors. Tests use an in-memory database and a fake mailer, so they do not send real email.

### Live API test with Postman CLI

This sends real email and creates a real account in the local database. The Postman desktop app is not required.

Install the CLI once:

```powershell
npm install -g postman-cli
postman --version
```

Start the API in another terminal:

```powershell
npm run dev
```

**Step 1 — send an OTP:**

```powershell
postman collection run postman/aravola-auth.postman_collection.json `
  -i "Request OTP" `
  --env-var "email=you@example.com"
```

**Step 2 — run the rest with the 6-digit code from the email:**

```powershell
postman collection run postman/aravola-auth.postman_collection.json `
  -i "Verify OTP" `
  -i "Create password" `
  -i "Login" `
  -i "Me" `
  -i "Logout" `
  -i "Me after logout" `
  --env-var "email=you@example.com" `
  --env-var "otp=123456" `
  --env-var "password=StrongPass1!"
```

Do **not** include `Request OTP` in step 2. It sends a new code and invalidates the one in `otp`.

The collection captures `verificationToken` and `sessionToken` between requests automatically. `Me after logout` is expected to return `401 SESSION_INVALID`, proving the session was revoked.

All requests use `http://127.0.0.1:3000` instead of `localhost`. This avoids the browser/cloud-agent local network block that can cause a `"Blocked address"` message in Postman Web.

If the account already exists, run only the returning-user requests:

```powershell
postman collection run postman/aravola-auth.postman_collection.json `
  -i "Login" `
  -i "Me" `
  -i "Logout" `
  -i "Me after logout" `
  --env-var "email=you@example.com" `
  --env-var "password=StrongPass1!"
```

`postman login` is not needed for a local run. The CLI warns that results are not published to Postman cloud, but all requests and tests still run.

To use the collection in the Postman app instead, import `postman/aravola-auth.postman_collection.json`, open **Variables**, and set `email`, `otp` and `password` before running the requests in order.
