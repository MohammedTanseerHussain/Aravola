import crypto from 'node:crypto';
import bcrypt from 'bcryptjs';
import { withTransaction } from './db.js';

export class ApiError extends Error {
  constructor(statusCode, code, message, details) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

const LOCAL_PART_RE = /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$/i;
const DOMAIN_LABEL_RE = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i;

function normalizeEmail(value) {
  if (typeof value !== 'string') throw new ApiError(400, 'INVALID_EMAIL', 'Please enter a valid email address.');
  const email = value.trim().toLowerCase();
  const parts = email.split('@');
  if (parts.length !== 2 || email.length > 254) throw new ApiError(400, 'INVALID_EMAIL', 'Please enter a valid email address.');
  const [local, domain] = parts;
  const labels = domain.split('.');
  const validLocal = local.length > 0 && local.length <= 64 && !local.startsWith('.') && !local.endsWith('.') && !local.includes('..') && LOCAL_PART_RE.test(local);
  const validDomain = labels.length >= 2 && domain.length <= 253 && labels.every((label) => label.length <= 63 && DOMAIN_LABEL_RE.test(label)) && /^[a-z]{2,63}$/i.test(labels.at(-1));
  if (!validLocal || !validDomain) throw new ApiError(400, 'INVALID_EMAIL', 'Please enter a valid email address.');
  return email;
}

function normalizeOtp(value) {
  const otp = typeof value === 'number' ? String(value) : typeof value === 'string' ? value.trim() : '';
  if (!/^\d{6}$/.test(otp)) throw new ApiError(400, 'INVALID_OTP_FORMAT', 'Enter the 6-digit code from the email.');
  return otp;
}

function normalizeVerificationToken(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{20,128}$/.test(value)) {
    throw new ApiError(400, 'INVALID_VERIFICATION_TOKEN', 'Your email verification session is missing or invalid. Verify your email again.');
  }
  return value;
}

function passwordPolicyErrors(password) {
  if (typeof password !== 'string') return [{ code: 'password_required', message: 'Password is required.' }];
  const errors = [];
  if ([...password].length < 8) errors.push({ code: 'min_length', message: 'Use at least 8 characters.' });
  if ([...password].length > 64) errors.push({ code: 'max_length', message: 'Use no more than 64 characters.' });
  if (Buffer.byteLength(password, 'utf8') > 72) errors.push({ code: 'max_bytes', message: 'The password is too long. Use fewer non-English characters.' });
  if (!/[A-Z]/.test(password)) errors.push({ code: 'uppercase', message: 'Include at least one uppercase letter (A-Z).' });
  if (!/[0-9]/.test(password)) errors.push({ code: 'number', message: 'Include at least one number (0-9).' });
  if (!/[^A-Za-z0-9\s]/.test(password)) errors.push({ code: 'special_character', message: 'Include at least one special character (for example ! @ # $ %).' });
  if (/\s/.test(password)) errors.push({ code: 'no_spaces', message: 'Spaces and tabs are not allowed.' });
  return errors;
}

function generateOtp() { return crypto.randomInt(100000, 1000000).toString(); }
function hashOtp(email, otp, pepper) { return crypto.createHmac('sha256', pepper).update(`signup:${email}:${otp}`).digest('hex'); }
function safeEqualHex(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false;
  const a = Buffer.from(left, 'hex'); const b = Buffer.from(right, 'hex');
  return a.length === b.length && a.length > 0 && crypto.timingSafeEqual(a, b);
}
function generateToken() { return crypto.randomBytes(32).toString('base64url'); }
function hashToken(token) { return crypto.createHash('sha256').update(token).digest('hex'); }
function redirectWithEmail(pageUrl, email) { const url = new URL(pageUrl); url.searchParams.set('email', email); return url.toString(); }
function publicUser(user) { return { id: user.id, email: user.email, createdAt: new Date(Number(user.created_at)).toISOString() }; }

export class AuthService {
  constructor({ db, mailer, config }) {
    this.db = db;
    this.mailer = mailer;
    this.config = config;
    this.dummyPasswordHash = bcrypt.hashSync('constant-timing-placeholder-password', this.config.password.bcryptRounds);
  }

  async requestSignupOtp(rawEmail) {
    const email = normalizeEmail(rawEmail);
    const now = Date.now();
    const result = await withTransaction(this.db, async (client) => {
      // Serialize signup requests for the same email, including the no-user-yet case.
      await client.query('SELECT pg_advisory_xact_lock(hashtext($1))', [email]);
      let { rows: [user] } = await client.query(
        `SELECT id, email, email_verified_at, password_hash, created_at
         FROM public.users WHERE lower(email) = $1 FOR UPDATE`, [email]);

      if (user?.password_hash) throw new ApiError(409, 'EMAIL_ALREADY_REGISTERED', 'An account with this email already exists.');
      if (!user) {
        const id = crypto.randomUUID();
        const inserted = await client.query(
          `INSERT INTO public.users (id, email, created_at, updated_at)
           VALUES ($1, $2, $3, $3) RETURNING id, email, created_at`, [id, email, now]);
        user = inserted.rows[0];
      }

      const latestResult = await client.query(
        `SELECT created_at FROM public.otp_codes WHERE user_id = $1
         ORDER BY created_at DESC, id DESC LIMIT 1`, [user.id]);
      const latest = latestResult.rows[0];
      const cooldownMs = this.config.otp.resendCooldownSeconds * 1000;
      if (latest && now - Number(latest.created_at) < cooldownMs) {
        const retryAfterSeconds = Math.max(1, Math.ceil((Number(latest.created_at) + cooldownMs - now) / 1000));
        throw new ApiError(429, 'OTP_RESEND_TOO_SOON', `Please wait ${retryAfterSeconds} seconds before requesting another code.`, { retryAfterSeconds });
      }

      const hourStart = now - 60 * 60 * 1000;
      const countResult = await client.query(
        `SELECT COUNT(*)::int AS count FROM public.otp_codes WHERE user_id = $1 AND created_at >= $2`, [user.id, hourStart]);
      if (countResult.rows[0].count >= this.config.otp.maxPerHour) {
        const oldestResult = await client.query(
          `SELECT created_at FROM public.otp_codes WHERE user_id = $1 AND created_at >= $2 ORDER BY created_at ASC, id ASC LIMIT 1`, [user.id, hourStart]);
        const retryAfterSeconds = Math.max(1, Math.ceil((Number(oldestResult.rows[0].created_at) + 60 * 60 * 1000 - now) / 1000));
        throw new ApiError(429, 'OTP_REQUEST_LIMIT_REACHED', 'Too many codes have been requested for this email. Try again later.', { retryAfterSeconds });
      }

      await client.query(
        `UPDATE public.otp_codes SET invalidated_at = $1
         WHERE user_id = $2 AND consumed_at IS NULL AND invalidated_at IS NULL`, [now, user.id]);
      const otp = generateOtp(); const otpId = crypto.randomUUID();
      const expiresAt = now + this.config.otp.expirySeconds * 1000;
      await client.query(
        `INSERT INTO public.otp_codes (id, user_id, code_hash, max_attempts, created_at, expires_at)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [otpId, user.id, hashOtp(email, otp, this.config.otp.pepper), this.config.otp.maxAttempts, now, expiresAt]);
      return { otp, otpId, user, expiresAt };
    });

    try {
      await this.mailer.sendOtpEmail({ to: email, otp: result.otp, expiresInMinutes: Math.ceil(this.config.otp.expirySeconds / 60) });
    } catch (error) {
      await this.db.query('DELETE FROM public.otp_codes WHERE id = $1', [result.otpId]);
      console.error(`[mail] Could not send a verification email: ${error.message}`);
      throw new ApiError(502, 'EMAIL_SEND_FAILED', 'We could not send the verification email. Please try again shortly.');
    }

    return { email, expiresInSeconds: this.config.otp.expirySeconds, resendAfterSeconds: this.config.otp.resendCooldownSeconds, redirectTo: redirectWithEmail(this.config.frontend.otpVerifyPage, email) };
  }

  async verifySignupOtp(rawEmail, rawOtp) {
    const email = normalizeEmail(rawEmail); const otp = normalizeOtp(rawOtp); const now = Date.now();
    const result = await withTransaction(this.db, async (client) => {
      const userResult = await client.query(
        `SELECT id, email, email_verified_at, password_hash, created_at FROM public.users WHERE lower(email) = $1 FOR UPDATE`, [email]);
      const user = userResult.rows[0];
      if (!user) return { error: new ApiError(400, 'OTP_INVALID_OR_EXPIRED', 'The code is incorrect or has expired. Request a new code.') };
      if (user.password_hash) return { error: new ApiError(409, 'EMAIL_ALREADY_REGISTERED', 'An account with this email already exists.') };

      const otpResult = await client.query(
        `SELECT id, user_id, code_hash, attempts, max_attempts, expires_at
         FROM public.otp_codes WHERE user_id = $1 AND consumed_at IS NULL AND invalidated_at IS NULL
         ORDER BY created_at DESC, id DESC LIMIT 1 FOR UPDATE`, [user.id]);
      const record = otpResult.rows[0];
      if (!record) return { error: new ApiError(400, 'OTP_INVALID_OR_EXPIRED', 'The code is incorrect or has expired. Request a new code.') };
      if (Number(record.expires_at) <= now) {
        await client.query('UPDATE public.otp_codes SET invalidated_at = $1 WHERE id = $2', [now, record.id]);
        return { error: new ApiError(400, 'OTP_EXPIRED', 'The code has expired. Request a new code.') };
      }
      if (record.attempts >= record.max_attempts) {
        await client.query('UPDATE public.otp_codes SET invalidated_at = $1 WHERE id = $2', [now, record.id]);
        return { error: new ApiError(429, 'OTP_ATTEMPTS_EXCEEDED', 'Too many incorrect attempts. Request a new code.', { mustRequestNewOtp: true }) };
      }
      if (!safeEqualHex(record.code_hash, hashOtp(email, otp, this.config.otp.pepper))) {
        const attempts = record.attempts + 1;
        await client.query('UPDATE public.otp_codes SET attempts = $1 WHERE id = $2', [attempts, record.id]);
        if (attempts >= record.max_attempts) {
          await client.query('UPDATE public.otp_codes SET invalidated_at = $1 WHERE id = $2', [now, record.id]);
          return { error: new ApiError(429, 'OTP_ATTEMPTS_EXCEEDED', 'Too many incorrect attempts. Request a new code.', { mustRequestNewOtp: true }) };
        }
        return { error: new ApiError(400, 'INVALID_OTP', 'The verification code is incorrect.', { attemptsRemaining: record.max_attempts - attempts }) };
      }

      await client.query('UPDATE public.otp_codes SET consumed_at = $1 WHERE id = $2', [now, record.id]);
      await client.query('UPDATE public.users SET email_verified_at = COALESCE(email_verified_at, $1), updated_at = $1 WHERE id = $2', [now, user.id]);
      await client.query('UPDATE public.verification_tokens SET used_at = $1 WHERE user_id = $2 AND used_at IS NULL', [now, user.id]);
      const verificationToken = generateToken();
      const expiresAt = now + this.config.verificationTokenExpirySeconds * 1000;
      await client.query(
        `INSERT INTO public.verification_tokens (id, user_id, token_hash, created_at, expires_at)
         VALUES ($1, $2, $3, $4, $5)`, [crypto.randomUUID(), user.id, hashToken(verificationToken), now, expiresAt]);
      return { verificationToken, expiresAt, user };
    });
    if (result.error) throw result.error;
    return { email, verificationToken: result.verificationToken, expiresInSeconds: this.config.verificationTokenExpirySeconds, redirectTo: redirectWithEmail(this.config.frontend.createPasswordPage, email) };
  }

  async createSession(client, userId, createdAt = Date.now()) {
    const sessionToken = generateToken(); const expiresAt = createdAt + this.config.sessionExpirySeconds * 1000;
    await client.query(
      `INSERT INTO public.sessions (id, user_id, token_hash, created_at, expires_at) VALUES ($1, $2, $3, $4, $5)`,
      [crypto.randomUUID(), userId, hashToken(sessionToken), createdAt, expiresAt]);
    return { sessionToken, sessionExpiresAt: new Date(expiresAt).toISOString() };
  }

  async createPassword(rawVerificationToken, password, confirmPassword) {
    const verificationToken = normalizeVerificationToken(rawVerificationToken);
    if (typeof password !== 'string' || typeof confirmPassword !== 'string') throw new ApiError(400, 'INVALID_REQUEST', 'Password and password confirmation are required.');
    const policyErrors = passwordPolicyErrors(password);
    if (policyErrors.length) throw new ApiError(400, 'WEAK_PASSWORD', 'Password does not meet the requirements.', { requirements: policyErrors });
    if (password !== confirmPassword) throw new ApiError(400, 'PASSWORD_MISMATCH', 'The two passwords do not match.');

    const passwordHash = await bcrypt.hash(password, this.config.password.bcryptRounds);
    const tokenHash = hashToken(verificationToken);
    const completed = await withTransaction(this.db, async (client) => {
      const now = Date.now();
      const tokenResult = await client.query(
        `SELECT vt.id, vt.user_id, vt.expires_at, vt.used_at, u.email, u.created_at AS user_created_at
         FROM public.verification_tokens vt JOIN public.users u ON u.id = vt.user_id
         WHERE vt.token_hash = $1 FOR UPDATE OF vt`, [tokenHash]);
      const token = tokenResult.rows[0];
      if (!token || token.used_at || Number(token.expires_at) <= now) throw new ApiError(400, 'VERIFICATION_EXPIRED', 'Your email verification has expired. Verify your email again.');

      const consumed = await client.query(
        `UPDATE public.verification_tokens SET used_at = $1 WHERE id = $2 AND used_at IS NULL AND expires_at > $1`, [now, token.id]);
      if (consumed.rowCount !== 1) throw new ApiError(400, 'VERIFICATION_EXPIRED', 'Your email verification has expired. Verify your email again.');
      const updated = await client.query(
        `UPDATE public.users SET password_hash = $1, updated_at = $2 WHERE id = $3 AND password_hash IS NULL`, [passwordHash, now, token.user_id]);
      if (updated.rowCount !== 1) throw new ApiError(409, 'EMAIL_ALREADY_REGISTERED', 'An account with this email already exists.');
      await client.query('UPDATE public.verification_tokens SET used_at = $1 WHERE user_id = $2 AND used_at IS NULL', [now, token.user_id]);
      const userResult = await client.query('SELECT id, email, created_at FROM public.users WHERE id = $1', [token.user_id]);
      const user = userResult.rows[0];
      const session = await this.createSession(client, user.id, now);
      return { user, session };
    });
    return { user: publicUser(completed.user), ...completed.session };
  }

  async login(rawEmail, password) {
    const email = normalizeEmail(rawEmail);
    if (typeof password !== 'string' || password.length === 0 || password.length > 1024) throw new ApiError(400, 'INVALID_REQUEST', 'Enter your email and password.');
    const result = await this.db.query(
      `SELECT id, email, email_verified_at, password_hash, created_at FROM public.users WHERE lower(email) = $1 LIMIT 1`, [email]);
    const user = result.rows[0];
    const matches = await bcrypt.compare(password, user?.password_hash || this.dummyPasswordHash);
    if (!user || !user.password_hash || !user.email_verified_at || !matches) throw new ApiError(401, 'INVALID_CREDENTIALS', 'Invalid email or password.');
    const session = await withTransaction(this.db, (client) => this.createSession(client, user.id));
    return { user: publicUser(user), ...session };
  }

  async authenticateSession(rawToken) {
    if (typeof rawToken !== 'string' || !/^[A-Za-z0-9_-]{20,128}$/.test(rawToken)) throw new ApiError(401, 'UNAUTHORIZED', 'A valid session token is required.');
    const result = await this.db.query(
      `SELECT s.expires_at AS session_expires_at, s.revoked_at, u.id AS user_id, u.email, u.created_at AS user_created_at
       FROM public.sessions s JOIN public.users u ON u.id = s.user_id WHERE s.token_hash = $1 LIMIT 1`, [hashToken(rawToken)]);
    const session = result.rows[0];
    if (!session || session.revoked_at || Number(session.session_expires_at) <= Date.now()) throw new ApiError(401, 'SESSION_INVALID', 'Your session is invalid or has expired.');
    return { user: publicUser({ id: session.user_id, email: session.email, created_at: session.user_created_at }), sessionExpiresAt: new Date(Number(session.session_expires_at)).toISOString() };
  }

  async logout(rawToken) {
    if (typeof rawToken === 'string' && /^[A-Za-z0-9_-]{20,128}$/.test(rawToken)) {
      await this.db.query('UPDATE public.sessions SET revoked_at = $1 WHERE token_hash = $2 AND revoked_at IS NULL', [Date.now(), hashToken(rawToken)]);
    }
  }
}
