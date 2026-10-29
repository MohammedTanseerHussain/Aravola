import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';
import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-rate-limit';
import { ApiError, AuthService } from './authService.js';
import { openDatabase } from './db.js';
import { createMailer } from './mailer.js';

/* -------------------------------------------------------------------------- */
/* Configuration                                                              */
/* -------------------------------------------------------------------------- */

function readInt(env, name, fallback, min, max) {
  const raw = env[name];
  if (raw === undefined || raw.trim() === '') return fallback;

  const value = Number(raw);
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`${name} must be a whole number between ${min} and ${max}.`);
  }
  return value;
}

function readBoolean(env, name, fallback) {
  const raw = env[name];
  if (raw === undefined || raw.trim() === '') return fallback;
  if (raw === 'true' || raw === '1') return true;
  if (raw === 'false' || raw === '0') return false;
  throw new Error(`${name} must be true or false.`);
}

function readUrl(env, name, fallback) {
  const raw = (env[name] || fallback).trim();
  let url;

  try {
    url = new URL(raw);
  } catch {
    throw new Error(`${name} must be a valid absolute URL.`);
  }

  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
    throw new Error(`${name} must be an http(s) URL without embedded credentials.`);
  }
  return url.toString();
}

function readCorsOrigins(env) {
  const raw = (env.CORS_ORIGINS || 'http://localhost:5173').trim();

  return raw.split(',').map((entry) => {
    const value = entry.trim();
    let url;

    try {
      url = new URL(value);
    } catch {
      throw new Error(`CORS_ORIGINS contains an invalid origin: ${value}`);
    }

    if (!['http:', 'https:'].includes(url.protocol) || url.pathname !== '/' || url.search || url.hash) {
      throw new Error('CORS_ORIGINS must contain origins only, for example https://app.example.com');
    }
    return url.origin;
  });
}

export function loadConfig(env = process.env) {
  const nodeEnv = (env.NODE_ENV || 'development').trim();
  const appName =
    (env.APP_NAME || 'Aravola').replace(/[\r\n]/g, ' ').trim().slice(0, 80) || 'Aravola';
  const otpPepper = env.OTP_PEPPER || '';

  if (otpPepper.length < 32 || /^(replace|change|your)[_-]/i.test(otpPepper)) {
    throw new Error(
      'OTP_PEPPER is required and must be random and at least 32 characters. Generate one with: ' +
        'node -e "console.log(require(\'crypto\').randomBytes(32).toString(\'hex\'))"',
    );
  }

  const databasePath = (env.DATABASE_PATH || './data/auth.db').trim();
  const smtpPort = readInt(env, 'SMTP_PORT', 587, 1, 65535);
  const smtpSecure = readBoolean(env, 'SMTP_SECURE', smtpPort === 465);
  const smtpAuthType = (env.SMTP_AUTH_TYPE || 'password').trim().toLowerCase();

  if (!['password', 'oauth2'].includes(smtpAuthType)) {
    throw new Error('SMTP_AUTH_TYPE must be "password" or "oauth2".');
  }

  return {
    nodeEnv,
    isProduction: nodeEnv === 'production',
    appName,
    port: readInt(env, 'PORT', 3000, 1, 65535),
    trustProxy: readInt(env, 'TRUST_PROXY', 0, 0, 10),
    corsOrigins: readCorsOrigins(env),
    databasePath:
      databasePath === ':memory:' || path.isAbsolute(databasePath)
        ? databasePath
        : path.resolve(process.cwd(), databasePath),
    frontend: {
      otpVerifyPage: readUrl(env, 'FRONTEND_OTP_VERIFY_URL', 'http://localhost:5173/verify-otp'),
      createPasswordPage: readUrl(
        env,
        'FRONTEND_CREATE_PASSWORD_URL',
        'http://localhost:5173/create-password',
      ),
    },
    otp: {
      pepper: otpPepper,
      expirySeconds: readInt(env, 'OTP_EXPIRY_MINUTES', 10, 1, 60) * 60,
      resendCooldownSeconds: readInt(env, 'OTP_RESEND_COOLDOWN_SECONDS', 60, 10, 3600),
      maxAttempts: readInt(env, 'OTP_MAX_ATTEMPTS', 5, 3, 10),
      maxPerHour: readInt(env, 'OTP_MAX_PER_HOUR', 5, 1, 30),
    },
    verificationTokenExpirySeconds:
      readInt(env, 'VERIFICATION_TOKEN_EXPIRY_MINUTES', 15, 1, 60) * 60,
    sessionExpirySeconds: readInt(env, 'SESSION_TTL_DAYS', 7, 1, 90) * 24 * 60 * 60,
    password: {
      bcryptRounds: readInt(env, 'BCRYPT_ROUNDS', 12, 10, 15),
    },
    mail: {
      authType: smtpAuthType,
      host: (env.SMTP_HOST || '').trim(),
      port: smtpPort,
      secure: smtpSecure,
      requireTls: readBoolean(env, 'SMTP_REQUIRE_TLS', !smtpSecure && smtpPort === 587),
      user: env.SMTP_USER || '',
      pass: env.SMTP_PASS || '',
      oauth2: {
        clientId: (env.SMTP_OAUTH_CLIENT_ID || '').trim(),
        clientSecret: env.SMTP_OAUTH_CLIENT_SECRET || '',
        refreshToken: env.SMTP_OAUTH_REFRESH_TOKEN || '',
      },
      from: (env.MAIL_FROM || '').trim(),
      replyTo: (env.MAIL_REPLY_TO || '').trim() || undefined,
      timeoutMs: readInt(env, 'SMTP_TIMEOUT_MS', 10000, 1000, 60000),
    },
    rateLimitEnabled: nodeEnv !== 'test',
  };
}

/* -------------------------------------------------------------------------- */
/* Helpers and rate limiting                                                  */
/* -------------------------------------------------------------------------- */

function asyncHandler(handler) {
  return (req, res, next) => Promise.resolve(handler(req, res, next)).catch(next);
}

function readBearerToken(req) {
  const match = /^Bearer ([A-Za-z0-9_-]{20,128})$/.exec(req.get('authorization') || '');
  if (!match) {
    throw new ApiError(401, 'UNAUTHORIZED', 'A valid session token is required.');
  }
  return match[1];
}

function noOp(_req, _res, next) {
  next();
}

function createLimiter({ windowMs, limit, message }) {
  return rateLimit({
    windowMs,
    limit,
    standardHeaders: 'draft-7',
    legacyHeaders: false,
    handler: (req, res, _next, options) => {
      const resetTime = req.rateLimit?.resetTime;
      const retryAfterSeconds = resetTime
        ? Math.max(1, Math.ceil((resetTime.getTime() - Date.now()) / 1000))
        : Math.ceil(windowMs / 1000);

      res.set('Retry-After', String(retryAfterSeconds));
      res.status(options.statusCode).json({
        ok: false,
        error: {
          code: 'RATE_LIMITED',
          message,
          details: { retryAfterSeconds },
        },
      });
    },
  });
}

function createRateLimiters(enabled) {
  if (!enabled) {
    return {
      global: noOp,
      requestOtp: noOp,
      verifyOtp: noOp,
      createPassword: noOp,
      login: noOp,
    };
  }

  return {
    global: createLimiter({
      windowMs: 15 * 60 * 1000,
      limit: 300,
      message: 'Too many requests from this address. Please try again later.',
    }),
    requestOtp: createLimiter({
      windowMs: 15 * 60 * 1000,
      limit: 10,
      message: 'Too many verification code requests. Please try again later.',
    }),
    verifyOtp: createLimiter({
      windowMs: 15 * 60 * 1000,
      limit: 30,
      message: 'Too many verification attempts. Please try again later.',
    }),
    createPassword: createLimiter({
      windowMs: 15 * 60 * 1000,
      limit: 20,
      message: 'Too many password attempts. Please try again later.',
    }),
    login: createLimiter({
      windowMs: 15 * 60 * 1000,
      limit: 20,
      message: 'Too many sign-in attempts. Please try again later.',
    }),
  };
}

/* -------------------------------------------------------------------------- */
/* Express app and API routes                                                 */
/* -------------------------------------------------------------------------- */

export function createApp({ config, db, mailer }) {
  const app = express();
  const authService = new AuthService({ config, db, mailer });
  const limiters = createRateLimiters(config.rateLimitEnabled);

  app.disable('x-powered-by');
  if (config.trustProxy > 0) app.set('trust proxy', config.trustProxy);

  app.use(helmet());
  app.use(
    cors({
      origin(origin, callback) {
        if (!origin || config.corsOrigins.includes(origin)) return callback(null, true);
        return callback(null, false);
      },
      methods: ['GET', 'POST', 'OPTIONS'],
      allowedHeaders: ['Content-Type', 'Authorization'],
      exposedHeaders: [
        'Retry-After',
        'RateLimit',
        'RateLimit-Policy',
        'RateLimit-Limit',
        'RateLimit-Remaining',
        'RateLimit-Reset',
      ],
      maxAge: 86400,
      credentials: false,
    }),
  );
  app.use(express.json({ limit: '16kb', strict: true }));

  app.get('/api/health', (_req, res) => {
    res.json({ ok: true, data: { status: 'healthy' } });
  });

  app.get('/api', (_req, res) => {
    res.json({
      ok: true,
      data: {
        name: config.appName,
        version: '1.0.0',
        endpoints: [
          'POST /api/auth/request-otp',
          'POST /api/auth/verify-otp',
          'POST /api/auth/create-password',
          'POST /api/auth/login',
          'GET /api/auth/me',
          'POST /api/auth/logout',
        ],
      },
    });
  });

  app.use('/api', limiters.global);

  app.post(
    '/api/auth/request-otp',
    limiters.requestOtp,
    asyncHandler(async (req, res) => {
      const data = await authService.requestSignupOtp(req.body?.email);
      res.status(200).json({
        ok: true,
        message: 'Verification code sent. Check your inbox and spam folder.',
        data,
      });
    }),
  );

  app.post('/api/auth/verify-otp', limiters.verifyOtp, (req, res) => {
    const data = authService.verifySignupOtp(req.body?.email, req.body?.otp);
    res.status(200).json({
      ok: true,
      message: 'Email verified successfully.',
      data,
    });
  });

  app.post(
    '/api/auth/create-password',
    limiters.createPassword,
    asyncHandler(async (req, res) => {
      const data = await authService.createPassword(
        req.body?.verificationToken,
        req.body?.password,
        req.body?.confirmPassword,
      );
      res.status(201).json({
        ok: true,
        message: 'Password created successfully. Your account is ready.',
        data,
      });
    }),
  );

  app.post(
    '/api/auth/login',
    limiters.login,
    asyncHandler(async (req, res) => {
      const data = await authService.login(req.body?.email, req.body?.password);
      res.status(200).json({ ok: true, message: 'Signed in successfully.', data });
    }),
  );

  app.get('/api/auth/me', (req, res) => {
    const data = authService.authenticateSession(readBearerToken(req));
    res.status(200).json({ ok: true, data });
  });

  app.post('/api/auth/logout', (req, res) => {
    const token = readBearerToken(req);
    authService.authenticateSession(token);
    authService.logout(token);
    res.status(200).json({ ok: true, message: 'Signed out successfully.' });
  });

  app.use((req, _res, next) => {
    next(new ApiError(404, 'NOT_FOUND', `No API route matches ${req.method} ${req.originalUrl}.`));
  });

  app.use((error, req, res, next) => {
    if (res.headersSent) return next(error);

    if (error.type === 'entity.parse.failed') {
      return res.status(400).json({
        ok: false,
        error: { code: 'INVALID_JSON', message: 'The request body is not valid JSON.' },
      });
    }

    if (error.type === 'entity.too.large') {
      return res.status(413).json({
        ok: false,
        error: { code: 'PAYLOAD_TOO_LARGE', message: 'The request body is too large.' },
      });
    }

    if (error instanceof ApiError) {
      return res.status(error.statusCode).json({
        ok: false,
        error: {
          code: error.code,
          message: error.message,
          ...(error.details ? { details: error.details } : {}),
        },
      });
    }

    console.error(`[server] ${req.method} ${req.originalUrl} failed:`, error);
    return res.status(500).json({
      ok: false,
      error: {
        code: 'INTERNAL_ERROR',
        message: 'Something went wrong on the server. Please try again.',
      },
    });
  });

  return app;
}

/* -------------------------------------------------------------------------- */
/* Startup                                                                    */
/* -------------------------------------------------------------------------- */

function start() {
  dotenv.config({ quiet: true });

  let config;
  let db;
  let mailer;

  try {
    config = loadConfig();
    db = openDatabase(config.databasePath);
    mailer = createMailer(config);
  } catch (error) {
    console.error(`[startup] ${error.message}`);
    process.exit(1);
  }

  const app = createApp({ config, db, mailer });
  const server = app.listen(config.port, () => {
    console.log(`[server] ${config.appName} auth API listening on http://localhost:${config.port}`);
    console.log(`[server] OTP page: ${config.frontend.otpVerifyPage}`);
    console.log(`[server] Password page: ${config.frontend.createPasswordPage}`);
  });

  mailer
    .verify()
    .then(() => console.log('[mail] SMTP connection verified.'))
    .catch((error) => {
      console.error(`[mail] SMTP verification failed: ${error.message}`);
      console.error('[mail] Check SMTP_HOST, port, credentials and MAIL_FROM before testing.');
    });

  function shutdown(signal) {
    console.log(`[server] ${signal} received, shutting down.`);
    server.close(() => {
      db.close();
      process.exit(0);
    });
    setTimeout(() => process.exit(1), 10000).unref();
  }

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

const isMainFile =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isMainFile) start();
