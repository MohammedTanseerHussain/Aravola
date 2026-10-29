import crypto from 'node:crypto';
import bcrypt from 'bcryptjs';

/*
 * All authentication logic lives in this file:
 *   1. Request validation and password rules
 *   2. OTP, verification-token and session-token cryptography
 *   3. AuthService: the database operations and signup/login flow
 *
 * HTTP routes are in server.js. The database schema is in db.js.
 */

/* -------------------------------------------------------------------------- */
/* Errors                                                                     */
/* -------------------------------------------------------------------------- */

export class ApiError extends Error {
  constructor(statusCode, code, message, details) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

/* -------------------------------------------------------------------------- */
/* Input validation                                                           */
/* -------------------------------------------------------------------------- */

const LOCAL_PART_RE = /^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+$/i;
const DOMAIN_LABEL_RE = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i;

function normalizeEmail(value) {
  if (typeof value !== 'string') {
    throw new ApiError(400, 'INVALID_EMAIL', 'Please enter a valid email address.');
  }

  const email = value.trim().toLowerCase();
  const parts = email.split('@');

  if (parts.length !== 2 || email.length > 254) {
    throw new ApiError(400, 'INVALID_EMAIL', 'Please enter a valid email address.');
  }

  const [local, domain] = parts;
  const labels = domain.split('.');
  const validLocal =
    local.length > 0 &&
    local.length <= 64 &&
    !local.startsWith('.') &&
    !local.endsWith('.') &&
    !local.includes('..') &&
    LOCAL_PART_RE.test(local);
  const validDomain =
    labels.length >= 2 &&
    domain.length <= 253 &&
    labels.every((label) => label.length <= 63 && DOMAIN_LABEL_RE.test(label)) &&
    /^[a-z]{2,63}$/i.test(labels.at(-1));

  if (!validLocal || !validDomain) {
    throw new ApiError(400, 'INVALID_EMAIL', 'Please enter a valid email address.');
  }

  return email;
}

function normalizeOtp(value) {
  const otp = typeof value === 'number' ? String(value) : typeof value === 'string' ? value.trim() : '';

  if (!/^\d{6}$/.test(otp)) {
    throw new ApiError(400, 'INVALID_OTP_FORMAT', 'Enter the 6-digit code from the email.');
  }
  return otp;
}

function normalizeVerificationToken(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{20,128}$/.test(value)) {
    throw new ApiError(
      400,
      'INVALID_VERIFICATION_TOKEN',
      'Your email verification session is missing or invalid. Verify your email again.',
    );
  }
  return value;
}

function passwordPolicyErrors(password) {
  if (typeof password !== 'string') {
    return [{ code: 'password_required', message: 'Password is required.' }];
  }

  const errors = [];
  const characterCount = [...password].length;

  if (characterCount < 8) {
    errors.push({ code: 'min_length', message: 'Use at least 8 characters.' });
  }
  if (characterCount > 64) {
    errors.push({ code: 'max_length', message: 'Use no more than 64 characters.' });
  }
  if (Buffer.byteLength(password, 'utf8') > 72) {
    errors.push({
      code: 'max_bytes',
      message: 'The password is too long. Use fewer non-English characters.',
    });
  }
  if (!/[A-Z]/.test(password)) {
    errors.push({ code: 'uppercase', message: 'Include at least one uppercase letter (A-Z).' });
  }
  if (!/[0-9]/.test(password)) {
    errors.push({ code: 'number', message: 'Include at least one number (0-9).' });
  }
  if (!/[^A-Za-z0-9\s]/.test(password)) {
    errors.push({
      code: 'special_character',
      message: 'Include at least one special character (for example ! @ # $ %).',
    });
  }
  if (/\s/.test(password)) {
    errors.push({ code: 'no_spaces', message: 'Spaces and tabs are not allowed.' });
  }

  return errors;
}

/* -------------------------------------------------------------------------- */
/* OTP and token cryptography                                                 */
/* -------------------------------------------------------------------------- */

function generateOtp() {
  return crypto.randomInt(100000, 1000000).toString();
}

function hashOtp(email, otp, pepper) {
  return crypto.createHmac('sha256', pepper).update(`signup:${email}:${otp}`).digest('hex');
}

function safeEqualHex(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false;

  const leftBuffer = Buffer.from(left, 'hex');
  const rightBuffer = Buffer.from(right, 'hex');

  return (
    leftBuffer.length === rightBuffer.length &&
    leftBuffer.length > 0 &&
    crypto.timingSafeEqual(leftBuffer, rightBuffer)
  );
}

function generateToken() {
  return crypto.randomBytes(32).toString('base64url');
}

function hashToken(token) {
  return crypto.createHash('sha256').update(token).digest('hex');
}

function redirectWithEmail(pageUrl, email) {
  const url = new URL(pageUrl);
  url.searchParams.set('email', email);
  return url.toString();
}

function publicUser(user) {
  return {
    id: user.id,
    email: user.email,
    createdAt: new Date(user.created_at).toISOString(),
  };
}

/* -------------------------------------------------------------------------- */
/* Auth service                                                               */
/* -------------------------------------------------------------------------- */

export class AuthService {
  constructor({ db, mailer, config }) {
    this.db = db;
    this.mailer = mailer;
    this.config = config;

    const s = {
      findUserByEmail: db.prepare(
        `SELECT id, email, email_verified_at, password_hash, created_at
         FROM users WHERE email = ?`,
      ),
      insertUser: db.prepare(
        `INSERT INTO users (id, email, created_at, updated_at) VALUES (?, ?, ?, ?)`,
      ),
      latestOtpForUser: db.prepare(
        `SELECT created_at FROM otp_codes
         WHERE user_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1`,
      ),
      otpCountSince: db.prepare(
        `SELECT COUNT(*) AS count FROM otp_codes WHERE user_id = ? AND created_at >= ?`,
      ),
      oldestOtpSince: db.prepare(
        `SELECT created_at FROM otp_codes
         WHERE user_id = ? AND created_at >= ? ORDER BY created_at ASC, rowid ASC LIMIT 1`,
      ),
      invalidateActiveOtps: db.prepare(
        `UPDATE otp_codes SET invalidated_at = ?
         WHERE user_id = ? AND consumed_at IS NULL AND invalidated_at IS NULL`,
      ),
      insertOtp: db.prepare(
        `INSERT INTO otp_codes
          (id, user_id, code_hash, max_attempts, created_at, expires_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
      ),
      deleteOtp: db.prepare(`DELETE FROM otp_codes WHERE id = ?`),
      latestActiveOtp: db.prepare(
        `SELECT id, user_id, code_hash, attempts, max_attempts, expires_at
         FROM otp_codes
         WHERE user_id = ? AND consumed_at IS NULL AND invalidated_at IS NULL
         ORDER BY created_at DESC, rowid DESC LIMIT 1`,
      ),
      setOtpAttempts: db.prepare(`UPDATE otp_codes SET attempts = ? WHERE id = ?`),
      markOtpInvalid: db.prepare(`UPDATE otp_codes SET invalidated_at = ? WHERE id = ?`),
      consumeOtp: db.prepare(
        `UPDATE otp_codes SET consumed_at = ? WHERE id = ? AND consumed_at IS NULL`,
      ),
      markEmailVerified: db.prepare(
        `UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ?
         WHERE id = ?`,
      ),
      invalidateVerificationTokens: db.prepare(
        `UPDATE verification_tokens SET used_at = ?
         WHERE user_id = ? AND used_at IS NULL`,
      ),
      insertVerificationToken: db.prepare(
        `INSERT INTO verification_tokens (id, user_id, token_hash, created_at, expires_at)
         VALUES (?, ?, ?, ?, ?)`,
      ),
      findVerificationByHash: db.prepare(
        `SELECT vt.id, vt.user_id, vt.expires_at, vt.used_at,
                u.email, u.password_hash, u.created_at AS user_created_at
         FROM verification_tokens vt
         JOIN users u ON u.id = vt.user_id
         WHERE vt.token_hash = ? LIMIT 1`,
      ),
      consumeVerificationToken: db.prepare(
        `UPDATE verification_tokens SET used_at = ?
         WHERE id = ? AND used_at IS NULL AND expires_at > ?`,
      ),
      setPassword: db.prepare(
        `UPDATE users SET password_hash = ?, updated_at = ?
         WHERE id = ? AND password_hash IS NULL`,
      ),
      findUserById: db.prepare(
        `SELECT id, email, email_verified_at, password_hash, created_at
         FROM users WHERE id = ?`,
      ),
      insertSession: db.prepare(
        `INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at)
         VALUES (?, ?, ?, ?, ?)`,
      ),
      findSessionByHash: db.prepare(
        `SELECT s.expires_at AS session_expires_at, s.revoked_at,
                u.id AS user_id, u.email, u.created_at AS user_created_at
         FROM sessions s
         JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = ? LIMIT 1`,
      ),
      revokeSession: db.prepare(
        `UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL`,
      ),
    };

    this.statements = s;
    this.dummyPasswordHash = bcrypt.hashSync(
      'constant-timing-placeholder-password',
      this.config.password.bcryptRounds,
    );

    this.requestOtpTransaction = db.transaction((email, now) => {
      let user = s.findUserByEmail.get(email);

      if (user?.password_hash) {
        throw new ApiError(
          409,
          'EMAIL_ALREADY_REGISTERED',
          'An account with this email already exists.',
        );
      }

      if (!user) {
        const id = crypto.randomUUID();
        s.insertUser.run(id, email, now, now);
        user = { id, email };
      }

      const latest = s.latestOtpForUser.get(user.id);
      const cooldownMs = this.config.otp.resendCooldownSeconds * 1000;

      if (latest && now - latest.created_at < cooldownMs) {
        const retryAfterSeconds = Math.max(
          1,
          Math.ceil((latest.created_at + cooldownMs - now) / 1000),
        );
        throw new ApiError(
          429,
          'OTP_RESEND_TOO_SOON',
          `Please wait ${retryAfterSeconds} seconds before requesting another code.`,
          { retryAfterSeconds },
        );
      }

      const hourStart = now - 60 * 60 * 1000;
      const { count } = s.otpCountSince.get(user.id, hourStart);

      if (count >= this.config.otp.maxPerHour) {
        const oldest = s.oldestOtpSince.get(user.id, hourStart);
        const retryAfterSeconds = Math.max(
          1,
          Math.ceil((oldest.created_at + 60 * 60 * 1000 - now) / 1000),
        );
        throw new ApiError(
          429,
          'OTP_REQUEST_LIMIT_REACHED',
          'Too many codes have been requested for this email. Try again later.',
          { retryAfterSeconds },
        );
      }

      s.invalidateActiveOtps.run(now, user.id);

      const otp = generateOtp();
      const otpId = crypto.randomUUID();
      const expiresAt = now + this.config.otp.expirySeconds * 1000;

      s.insertOtp.run(
        otpId,
        user.id,
        hashOtp(email, otp, this.config.otp.pepper),
        this.config.otp.maxAttempts,
        now,
        expiresAt,
      );

      return { otp, otpId, user, expiresAt };
    });

    this.verifyOtpTransaction = db.transaction((email, otp, now) => {
      const user = s.findUserByEmail.get(email);

      if (!user) {
        return {
          error: new ApiError(
            400,
            'OTP_INVALID_OR_EXPIRED',
            'The code is incorrect or has expired. Request a new code.',
          ),
        };
      }

      if (user.password_hash) {
        return {
          error: new ApiError(
            409,
            'EMAIL_ALREADY_REGISTERED',
            'An account with this email already exists.',
          ),
        };
      }

      const record = s.latestActiveOtp.get(user.id);

      if (!record) {
        return {
          error: new ApiError(
            400,
            'OTP_INVALID_OR_EXPIRED',
            'The code is incorrect or has expired. Request a new code.',
          ),
        };
      }

      if (record.expires_at <= now) {
        s.markOtpInvalid.run(now, record.id);
        return {
          error: new ApiError(400, 'OTP_EXPIRED', 'The code has expired. Request a new code.'),
        };
      }

      if (record.attempts >= record.max_attempts) {
        s.markOtpInvalid.run(now, record.id);
        return {
          error: new ApiError(
            429,
            'OTP_ATTEMPTS_EXCEEDED',
            'Too many incorrect attempts. Request a new code.',
            { mustRequestNewOtp: true },
          ),
        };
      }

      const suppliedHash = hashOtp(email, otp, this.config.otp.pepper);

      if (!safeEqualHex(record.code_hash, suppliedHash)) {
        const attempts = record.attempts + 1;
        s.setOtpAttempts.run(attempts, record.id);

        if (attempts >= record.max_attempts) {
          s.markOtpInvalid.run(now, record.id);
          return {
            error: new ApiError(
              429,
              'OTP_ATTEMPTS_EXCEEDED',
              'Too many incorrect attempts. Request a new code.',
              { mustRequestNewOtp: true },
            ),
          };
        }

        return {
          error: new ApiError(400, 'INVALID_OTP', 'The verification code is incorrect.', {
            attemptsRemaining: record.max_attempts - attempts,
          }),
        };
      }

      s.consumeOtp.run(now, record.id);
      s.markEmailVerified.run(now, now, user.id);
      s.invalidateVerificationTokens.run(now, user.id);

      const verificationToken = generateToken();
      const expiresAt = now + this.config.verificationTokenExpirySeconds * 1000;

      s.insertVerificationToken.run(
        crypto.randomUUID(),
        user.id,
        hashToken(verificationToken),
        now,
        expiresAt,
      );

      return { verificationToken, expiresAt, user };
    });
  }

  createSession(userId, createdAt = Date.now()) {
    const sessionToken = generateToken();
    const expiresAt = createdAt + this.config.sessionExpirySeconds * 1000;

    this.statements.insertSession.run(
      crypto.randomUUID(),
      userId,
      hashToken(sessionToken),
      createdAt,
      expiresAt,
    );

    return {
      sessionToken,
      sessionExpiresAt: new Date(expiresAt).toISOString(),
    };
  }

  async requestSignupOtp(rawEmail) {
    const email = normalizeEmail(rawEmail);
    const now = Date.now();
    const result = this.requestOtpTransaction(email, now);
    const expiresInMinutes = Math.ceil(this.config.otp.expirySeconds / 60);

    try {
      await this.mailer.sendOtpEmail({
        to: email,
        otp: result.otp,
        expiresInMinutes,
      });
    } catch (error) {
      this.statements.deleteOtp.run(result.otpId);
      console.error(`[mail] Could not send a verification email: ${error.message}`);
      throw new ApiError(
        502,
        'EMAIL_SEND_FAILED',
        'We could not send the verification email. Please try again shortly.',
      );
    }

    return {
      email,
      expiresInSeconds: this.config.otp.expirySeconds,
      resendAfterSeconds: this.config.otp.resendCooldownSeconds,
      redirectTo: redirectWithEmail(this.config.frontend.otpVerifyPage, email),
    };
  }

  verifySignupOtp(rawEmail, rawOtp) {
    const email = normalizeEmail(rawEmail);
    const otp = normalizeOtp(rawOtp);
    const result = this.verifyOtpTransaction(email, otp, Date.now());

    if (result.error) throw result.error;

    return {
      email,
      verificationToken: result.verificationToken,
      expiresInSeconds: this.config.verificationTokenExpirySeconds,
      redirectTo: redirectWithEmail(this.config.frontend.createPasswordPage, email),
    };
  }

  async createPassword(rawVerificationToken, password, confirmPassword) {
    const verificationToken = normalizeVerificationToken(rawVerificationToken);

    if (typeof password !== 'string' || typeof confirmPassword !== 'string') {
      throw new ApiError(400, 'INVALID_REQUEST', 'Password and password confirmation are required.');
    }

    const policyErrors = passwordPolicyErrors(password);

    if (policyErrors.length > 0) {
      throw new ApiError(400, 'WEAK_PASSWORD', 'Password does not meet the requirements.', {
        requirements: policyErrors,
      });
    }

    if (password !== confirmPassword) {
      throw new ApiError(400, 'PASSWORD_MISMATCH', 'The two passwords do not match.');
    }

    const tokenHash = hashToken(verificationToken);
    const now = Date.now();
    const tokenRecord = this.statements.findVerificationByHash.get(tokenHash);

    if (!tokenRecord || tokenRecord.used_at || tokenRecord.expires_at <= now) {
      throw new ApiError(
        400,
        'VERIFICATION_EXPIRED',
        'Your email verification has expired. Verify your email again.',
      );
    }

    if (tokenRecord.password_hash) {
      throw new ApiError(
        409,
        'EMAIL_ALREADY_REGISTERED',
        'An account with this email already exists.',
      );
    }

    const passwordHash = await bcrypt.hash(password, this.config.password.bcryptRounds);

    const completed = this.db.transaction(() => {
      const currentTime = Date.now();
      const consumed = this.statements.consumeVerificationToken.run(
        currentTime,
        tokenRecord.id,
        currentTime,
      );

      if (consumed.changes !== 1) {
        throw new ApiError(
          400,
          'VERIFICATION_EXPIRED',
          'Your email verification has expired. Verify your email again.',
        );
      }

      const updated = this.statements.setPassword.run(passwordHash, currentTime, tokenRecord.user_id);

      if (updated.changes !== 1) {
        throw new ApiError(
          409,
          'EMAIL_ALREADY_REGISTERED',
          'An account with this email already exists.',
        );
      }

      this.statements.invalidateVerificationTokens.run(currentTime, tokenRecord.user_id);

      const user = this.statements.findUserById.get(tokenRecord.user_id);
      return { user, session: this.createSession(user.id, currentTime) };
    })();

    return { user: publicUser(completed.user), ...completed.session };
  }

  async login(rawEmail, password) {
    const email = normalizeEmail(rawEmail);

    if (typeof password !== 'string' || password.length === 0 || password.length > 1024) {
      throw new ApiError(400, 'INVALID_REQUEST', 'Enter your email and password.');
    }

    const user = this.statements.findUserByEmail.get(email);
    const hash = user?.password_hash || this.dummyPasswordHash;
    const passwordMatches = await bcrypt.compare(password, hash);

    if (!user || !user.password_hash || !passwordMatches) {
      throw new ApiError(401, 'INVALID_CREDENTIALS', 'Invalid email or password.');
    }

    const session = this.createSession(user.id);
    return { user: publicUser(user), ...session };
  }

  authenticateSession(rawToken) {
    if (typeof rawToken !== 'string' || !/^[A-Za-z0-9_-]{20,128}$/.test(rawToken)) {
      throw new ApiError(401, 'UNAUTHORIZED', 'A valid session token is required.');
    }

    const session = this.statements.findSessionByHash.get(hashToken(rawToken));

    if (!session || session.revoked_at || session.session_expires_at <= Date.now()) {
      throw new ApiError(401, 'SESSION_INVALID', 'Your session is invalid or has expired.');
    }

    return {
      user: publicUser({
        id: session.user_id,
        email: session.email,
        created_at: session.user_created_at,
      }),
      sessionExpiresAt: new Date(session.session_expires_at).toISOString(),
    };
  }

  logout(rawToken) {
    if (typeof rawToken === 'string' && /^[A-Za-z0-9_-]{20,128}$/.test(rawToken)) {
      this.statements.revokeSession.run(Date.now(), hashToken(rawToken));
    }
  }
}
