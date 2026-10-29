# API guide

Base URL in local development: `http://localhost:3000`

This document is for the React developer integrating with the backend.

## Response format

All requests and responses use JSON.

Success:

```json
{
  "ok": true,
  "message": "Human-readable message",
  "data": {}
}
```

Error:

```json
{
  "ok": false,
  "error": {
    "code": "MACHINE_READABLE_CODE",
    "message": "Safe to display to the user",
    "details": {}
  }
}
```

`details` is optional.

## Signup flow

The UI collects the email and password first. The password stays in the React app until the email is verified, so the backend never stores a password for an unverified address.

```text
React page 1: email + password + confirmation
        ↓  POST /api/auth/request-otp { email }
React page 2: OTP verification
        ↓  POST /api/auth/verify-otp { email, otp }
        ↓  data.verificationToken
        ↓  POST /api/auth/create-password { verificationToken, password, confirmPassword }
        ↓  data.sessionToken
Signed-in app
```

- `request-otp` receives only the email. It sends the OTP and returns `expiresInSeconds` and `resendAfterSeconds`.
- The React app holds `email`, `password` and `confirmPassword` in memory between page 1 and page 2.
- After `verify-otp` succeeds, call `create-password` immediately with the held password and the returned `verificationToken`.
- `create-password` is the point where the backend saves the password. It does not have to be a separate screen.
- The backend does **not** resend automatically. When the 10-minute timer reaches zero, show a **Resend code** button. Only call `request-otp` again when the user clicks it.
- If the OTP page is refreshed, the in-memory password is lost. Send the user back to page 1. Storing the password in `sessionStorage` for the short signup window is possible but less secure.

The backend returns page URLs but does not navigate the browser. React must perform the navigation with `window.location.assign(...)` or React Router.

- `request-otp.data.redirectTo` → OTP page.
- `verify-otp.data.redirectTo` → optional separate create-password page. In the password-first flow, ignore it and call `create-password` directly.

The page URLs come from:

```dotenv
FRONTEND_OTP_VERIFY_URL=http://localhost:5173/verify-otp
FRONTEND_CREATE_PASSWORD_URL=http://localhost:5173/create-password
```

`FRONTEND_CREATE_PASSWORD_URL` is optional. It is only used by clients that keep a separate password page after OTP verification.

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/request-otp` | Send a signup OTP |
| POST | `/api/auth/verify-otp` | Verify OTP and get a one-time verification token |
| POST | `/api/auth/create-password` | Save the password and receive a session |
| POST | `/api/auth/login` | Sign in with email and password |
| GET | `/api/auth/me` | Get the current user |
| POST | `/api/auth/logout` | Revoke the current session |
| GET | `/api/health` | Health check |

---

## POST `/api/auth/request-otp`

Sends a 6-digit OTP. Call it when the user clicks **Next** from the email/password page.

Calling it again resends a code after the cooldown and invalidates the previous code. The backend never sends another code automatically.

### Request

```json
{
  "email": "user@example.com"
}
```

### Success — `200`

```json
{
  "ok": true,
  "message": "Verification code sent. Check your inbox and spam folder.",
  "data": {
    "email": "user@example.com",
    "expiresInSeconds": 600,
    "resendAfterSeconds": 60,
    "redirectTo": "http://localhost:5173/verify-otp?email=user%40example.com"
  }
}
```

The OTP is never returned by the API. It is stored only as a hash and expires after 10 minutes by default.

### Resend and expiry

- `expiresInSeconds` is the OTP lifetime (600 seconds by default).
- `resendAfterSeconds` is the cooldown before another request (60 seconds by default).
- The backend does **not** send a replacement code when the OTP expires.
- Show a countdown in React. When it reaches zero, show **Code expired** and a **Resend code** button.
- On resend, call this endpoint again. The previous code is invalidated.
- If the user clicks too early, the API returns `429 OTP_RESEND_TOO_SOON`; use `details.retryAfterSeconds`.
- If the user has requested too many codes, the API returns `429 OTP_REQUEST_LIMIT_REACHED`.

### Errors

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `INVALID_EMAIL` | Missing or invalid email |
| 409 | `EMAIL_ALREADY_REGISTERED` | An account with this email already exists |
| 429 | `OTP_RESEND_TOO_SOON` | Wait `details.retryAfterSeconds` |
| 429 | `OTP_REQUEST_LIMIT_REACHED` | Too many codes requested for this email |
| 429 | `RATE_LIMITED` | Too many requests from this IP |
| 502 | `EMAIL_SEND_FAILED` | SMTP failed; the OTP was discarded so the user can retry |

---

## POST `/api/auth/verify-otp`

### Request

```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

Keep `otp` as a string in React so leading zeros are preserved.

### Success — `200`

```json
{
  "ok": true,
  "message": "Email verified successfully.",
  "data": {
    "email": "user@example.com",
    "verificationToken": "a-long-random-token",
    "expiresInSeconds": 900,
    "redirectTo": "http://localhost:5173/create-password?email=user%40example.com"
  }
}
```

The `redirectTo` field points to the optional separate create-password page. In the password-first flow, ignore it and call `create-password` directly.

The verification token:

- is required for the final `create-password` call
- is single-use
- expires after 15 minutes by default
- must not be put in a URL, analytics event or log
- can stay in a local variable or React state; in the password-first flow it is used immediately

### Errors

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `INVALID_OTP_FORMAT` | OTP is not exactly six digits |
| 400 | `OTP_EXPIRED` | Request a new code |
| 400 | `OTP_INVALID_OR_EXPIRED` | Wrong, used or missing code |
| 400 | `INVALID_OTP` | Wrong code; see `details.attemptsRemaining` |
| 429 | `OTP_ATTEMPTS_EXCEEDED` | Request a new code |
| 429 | `RATE_LIMITED` | Too many attempts from this IP |

After the maximum number of wrong attempts, the code is invalidated even if the next attempt is correct.

---

## POST `/api/auth/create-password`

In the password-first flow, call this immediately after `verify-otp`. The password and confirmation were collected on page 1 and held in React state.

### Request

```json
{
  "verificationToken": "the-token-from-verify-otp",
  "password": "StrongPass1!",
  "confirmPassword": "StrongPass1!"
}
```

### Password rules

- 8–64 characters
- at least one uppercase letter (`A-Z`)
- at least one number (`0-9`)
- at least one special character, for example `! @ # $ %`
- no spaces or other whitespace
- must match `confirmPassword`
- maximum 72 UTF-8 bytes for bcrypt compatibility

### Success — `201`

```json
{
  "ok": true,
  "message": "Password created successfully. Your account is ready.",
  "data": {
    "user": {
      "id": "a-uuid",
      "email": "user@example.com",
      "createdAt": "2026-10-26T12:00:00.000Z"
    },
    "sessionToken": "a-long-random-session-token",
    "sessionExpiresAt": "2026-11-02T12:00:00.000Z"
  }
}
```

The account is automatically signed in after password creation.

### Errors

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | Password or confirmation is missing |
| 400 | `WEAK_PASSWORD` | See `details.requirements` |
| 400 | `PASSWORD_MISMATCH` | The two passwords differ |
| 400 | `INVALID_VERIFICATION_TOKEN` | Missing or malformed token |
| 400 | `VERIFICATION_EXPIRED` | Token expired or was already used; verify again |
| 409 | `EMAIL_ALREADY_REGISTERED` | The account already exists |
| 429 | `RATE_LIMITED` | Too many attempts from this IP |

Example weak-password response:

```json
{
  "ok": false,
  "error": {
    "code": "WEAK_PASSWORD",
    "message": "Password does not meet the requirements.",
    "details": {
      "requirements": [
        {
          "code": "uppercase",
          "message": "Include at least one uppercase letter (A-Z)."
        },
        {
          "code": "number",
          "message": "Include at least one number (0-9)."
        }
      ]
    }
  }
}
```

Possible requirement codes:

`password_required`, `min_length`, `max_length`, `max_bytes`, `uppercase`, `number`, `special_character`, `no_spaces`.

---

## POST `/api/auth/login`

### Request

```json
{
  "email": "user@example.com",
  "password": "StrongPass1!"
}
```

### Success — `200`

```json
{
  "ok": true,
  "message": "Signed in successfully.",
  "data": {
    "user": {
      "id": "a-uuid",
      "email": "user@example.com",
      "createdAt": "2026-10-26T12:00:00.000Z"
    },
    "sessionToken": "a-long-random-session-token",
    "sessionExpiresAt": "2026-11-02T12:00:00.000Z"
  }
}
```

### Errors

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `INVALID_EMAIL` | Missing or invalid email |
| 400 | `INVALID_REQUEST` | Password is missing |
| 401 | `INVALID_CREDENTIALS` | Wrong email or password |
| 429 | `RATE_LIMITED` | Too many sign-in attempts from this IP |

---

## GET `/api/auth/me`

Send the session token as a bearer credential:

```http
GET /api/auth/me
Authorization: Bearer <sessionToken>
```

### Success — `200`

```json
{
  "ok": true,
  "data": {
    "user": {
      "id": "a-uuid",
      "email": "user@example.com",
      "createdAt": "2026-10-26T12:00:00.000Z"
    },
    "sessionExpiresAt": "2026-11-02T12:00:00.000Z"
  }
}
```

### Errors

| Status | Code | Meaning |
| --- | --- | --- |
| 401 | `UNAUTHORIZED` | Missing or malformed bearer token |
| 401 | `SESSION_INVALID` | Expired, revoked or unknown session |

---

## POST `/api/auth/logout`

Requires `Authorization: Bearer <sessionToken>`.

### Success — `200`

```json
{
  "ok": true,
  "message": "Signed out successfully."
}
```

After logout, requests with that token return `401 SESSION_INVALID`.

---

## GET `/api/health`

No authentication required.

```json
{
  "ok": true,
  "data": {
    "status": "healthy"
  }
}
```

---

## React integration

Set the API URL in the React `.env`:

```dotenv
VITE_API_URL=http://localhost:3000
```

### API helper

```js
const API_URL = import.meta.env.VITE_API_URL;

export class ApiError extends Error {
  constructor(payload, status) {
    super(payload?.error?.message || 'Request failed');
    this.name = 'ApiError';
    this.status = status;
    this.code = payload?.error?.code;
    this.details = payload?.error?.details;
  }
}

async function apiRequest(path, { method = 'GET', body, token } = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new ApiError(payload, response.status);
  }

  return payload;
}

export const authApi = {
  requestOtp: (email) =>
    apiRequest('/api/auth/request-otp', { method: 'POST', body: { email } }),

  verifyOtp: (email, otp) =>
    apiRequest('/api/auth/verify-otp', { method: 'POST', body: { email, otp } }),

  createPassword: (verificationToken, password, confirmPassword) =>
    apiRequest('/api/auth/create-password', {
      method: 'POST',
      body: { verificationToken, password, confirmPassword },
    }),

  login: (email, password) =>
    apiRequest('/api/auth/login', { method: 'POST', body: { email, password } }),

  me: (token) => apiRequest('/api/auth/me', { token }),

  logout: (token) =>
    apiRequest('/api/auth/logout', { method: 'POST', token }),
};
```

### Page 1 — email and password

The backend sends the OTP only when the user clicks **Next**. Keep the password in React state so it survives the navigation to the OTP page.

```jsx
// SignupPage.jsx
try {
  const { data } = await authApi.requestOtp(email.trim().toLowerCase());
  setSignup({ email: data.email, password, confirmPassword });
  navigate(`/verify-otp?email=${encodeURIComponent(data.email)}`, {
    state: {
      expiresInSeconds: data.expiresInSeconds,
      resendAfterSeconds: data.resendAfterSeconds,
    },
  });
} catch (error) {
  if (error.code === 'EMAIL_ALREADY_REGISTERED') {
    setError('An account already exists. Sign in instead.');
  } else {
    setError(error.message);
  }
}
```

Validate the password and confirmation on page 1 with the same rules before calling `request-otp`. The backend does not receive the password until `create-password`, so a weak password would otherwise fail only after the user verifies the OTP.

`setSignup` must live in a provider that wraps both the signup and OTP routes. If it only wraps the signup page, the password is lost on navigation.

### Page 2 — verify code and create the account

```jsx
// VerifyOtpPage.jsx
try {
  const verified = await authApi.verifyOtp(signup.email, otp);

  const created = await authApi.createPassword(
    verified.data.verificationToken,
    signup.password,
    signup.confirmPassword,
  );

  sessionStorage.setItem('sessionToken', created.data.sessionToken);
  navigate('/app');
} catch (error) {
  if (error.code === 'INVALID_OTP') {
    setError(`${error.message} Attempts left: ${error.details.attemptsRemaining}.`);
  } else if (error.code === 'OTP_EXPIRED') {
    setError('Code expired. Click Resend code.');
  } else {
    setError(error.message);
  }
}
```

### OTP countdown and resend

Use the values returned by `request-otp`. Do not call the API when the timer reaches zero; wait for the user to click **Resend code**.

```jsx
const [expiresIn, setExpiresIn] = useState(initialExpiresIn); // 600
const [resendIn, setResendIn] = useState(initialResendAfter); // 60

useEffect(() => {
  const timer = setInterval(() => {
    setExpiresIn((value) => Math.max(0, value - 1));
    setResendIn((value) => Math.max(0, value - 1));
  }, 1000);
  return () => clearInterval(timer);
}, []);

async function handleResend() {
  if (resendIn > 0) return;

  try {
    const { data } = await authApi.requestOtp(signup.email);
    setExpiresIn(data.expiresInSeconds);
    setResendIn(data.resendAfterSeconds);
    setOtp('');
    setError('');
  } catch (error) {
    if (error.code === 'OTP_RESEND_TOO_SOON') {
      setResendIn(error.details.retryAfterSeconds);
    } else {
      setError(error.message);
    }
  }
}
```

The backend invalidates the previous code when a new one is sent. The frontend must also clear the old OTP input.

### Signup state

```jsx
const [signup, setSignup] = useState({
  email: '',
  password: '',
  confirmPassword: '',
});
```

Keep this in React state or context. Do not use `localStorage` for the password. Clear it after `create-password` succeeds. If the OTP page is refreshed and the state is gone, send the user back to page 1.

### Authenticated requests

```js
const sessionToken = sessionStorage.getItem('sessionToken');
const { data } = await authApi.me(sessionToken);
```

## Token storage

- Verification token: one-time only; use it immediately in the password-first flow. Do not put it in a URL or `localStorage`.
- Signup password: keep it in React state or context until `create-password` succeeds. Do not put it in `localStorage`.
- Session token: bearer credential; send it only over HTTPS in production.
- Avoid placing tokens in URLs or logs.
- `localStorage` persists across restarts but is readable by injected JavaScript. Prefer `sessionStorage` or an in-memory store.
