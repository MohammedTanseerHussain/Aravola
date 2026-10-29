import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp, loadConfig } from '../src/server.js';
import { openDatabase } from '../src/db.js';

function createTestContext() {
  const config = loadConfig({
    NODE_ENV: 'test',
    APP_NAME: 'Aravola Test',
    OTP_PEPPER: 'test-pepper-that-is-longer-than-thirty-two-characters',
    BCRYPT_ROUNDS: '10',
    FRONTEND_OTP_VERIFY_URL: 'http://localhost:5173/verify-otp',
    FRONTEND_CREATE_PASSWORD_URL: 'http://localhost:5173/create-password',
  });

  const db = openDatabase(':memory:');
  const mailer = {
    sent: [],
    shouldFail: false,
    async sendOtpEmail(message) {
      if (this.shouldFail) {
        throw new Error('simulated SMTP failure');
      }
      this.sent.push(message);
    },
  };
  const app = createApp({ config, db, mailer });

  return { app, db, mailer, config };
}

async function startSignup(app, mailer, db) {
  const response = await request(app)
    .post('/api/auth/request-otp')
    .send({ email: 'User@Gmail.com ' });

  assert.equal(response.status, 200);
  assert.equal(response.body.data.email, 'user@gmail.com');
  assert.equal(mailer.sent.length, 1);

  const otp = mailer.sent[0].otp;
  const stored = db.prepare('SELECT code_hash FROM otp_codes LIMIT 1').get();
  assert.notEqual(stored.code_hash, otp);
  assert.match(stored.code_hash, /^[a-f0-9]{64}$/);

  return { response, otp };
}

test('full signup flow: request OTP, verify, create password', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  const { response: otpResponse, otp } = await startSignup(app, mailer, db);

  assert.match(otp, /^\d{6}$/);
  assert.match(otpResponse.body.data.redirectTo, /verify-otp\?email=user%40gmail\.com/);
  assert.equal(JSON.stringify(otpResponse.body).includes(otp), false);

  const wrong = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp: '999999' === otp ? '111111' : '999999' });

  assert.equal(wrong.status, 400);
  assert.equal(wrong.body.error.code, 'INVALID_OTP');
  assert.equal(wrong.body.error.details.attemptsRemaining, 4);

  const verified = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp });

  assert.equal(verified.status, 200);
  assert.ok(verified.body.data.verificationToken);
  assert.match(verified.body.data.redirectTo, /create-password\?email=user%40gmail\.com/);

  const weak = await request(app)
    .post('/api/auth/create-password')
    .send({
      verificationToken: verified.body.data.verificationToken,
      password: 'alllowercase1!',
      confirmPassword: 'alllowercase1!',
    });

  assert.equal(weak.status, 400);
  assert.equal(weak.body.error.code, 'WEAK_PASSWORD');

  const mismatch = await request(app)
    .post('/api/auth/create-password')
    .send({
      verificationToken: verified.body.data.verificationToken,
      password: 'GoodPass1!',
      confirmPassword: 'GoodPass2!',
    });

  assert.equal(mismatch.status, 400);
  assert.equal(mismatch.body.error.code, 'PASSWORD_MISMATCH');

  const created = await request(app)
    .post('/api/auth/create-password')
    .send({
      verificationToken: verified.body.data.verificationToken,
      password: 'GoodPass1!',
      confirmPassword: 'GoodPass1!',
    });

  assert.equal(created.status, 201);
  assert.equal(created.body.data.user.email, 'user@gmail.com');
  assert.ok(created.body.data.sessionToken);

  const stored = db
    .prepare('SELECT password_hash FROM users WHERE email = ?')
    .get('user@gmail.com');
  assert.match(stored.password_hash, /^\$2[aby]\$/);
  assert.equal(stored.password_hash.includes('GoodPass1!'), false);

  const wrongLogin = await request(app)
    .post('/api/auth/login')
    .send({ email: 'user@gmail.com', password: 'WrongPass1!' });
  assert.equal(wrongLogin.status, 401);
  assert.equal(wrongLogin.body.error.code, 'INVALID_CREDENTIALS');

  const login = await request(app)
    .post('/api/auth/login')
    .send({ email: 'USER@gmail.com', password: 'GoodPass1!' });
  assert.equal(login.status, 200);
  assert.ok(login.body.data.sessionToken);

  const me = await request(app)
    .get('/api/auth/me')
    .set('Authorization', `Bearer ${login.body.data.sessionToken}`);
  assert.equal(me.status, 200);
  assert.equal(me.body.data.user.email, 'user@gmail.com');

  const logout = await request(app)
    .post('/api/auth/logout')
    .set('Authorization', `Bearer ${login.body.data.sessionToken}`);
  assert.equal(logout.status, 200);

  const meAfterLogout = await request(app)
    .get('/api/auth/me')
    .set('Authorization', `Bearer ${login.body.data.sessionToken}`);
  assert.equal(meAfterLogout.status, 401);
  assert.equal(meAfterLogout.body.error.code, 'SESSION_INVALID');

  const reused = await request(app)
    .post('/api/auth/create-password')
    .send({
      verificationToken: verified.body.data.verificationToken,
      password: 'AnotherPass1!',
      confirmPassword: 'AnotherPass1!',
    });

  assert.equal(reused.status, 400);
  assert.equal(reused.body.error.code, 'VERIFICATION_EXPIRED');

  const duplicate = await request(app)
    .post('/api/auth/request-otp')
    .send({ email: 'user@gmail.com' });

  assert.equal(duplicate.status, 409);
  assert.equal(duplicate.body.error.code, 'EMAIL_ALREADY_REGISTERED');
});

test('rejects invalid email and invalid OTP format', async (t) => {
  const { app, db } = createTestContext();
  t.after(() => db.close());

  const emailResponse = await request(app)
    .post('/api/auth/request-otp')
    .send({ email: 'not-an-email' });

  assert.equal(emailResponse.status, 400);
  assert.equal(emailResponse.body.error.code, 'INVALID_EMAIL');

  const otpResponse = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp: '123' });

  assert.equal(otpResponse.status, 400);
  assert.equal(otpResponse.body.error.code, 'INVALID_OTP_FORMAT');
});

test('enforces password policy rules and confirmation', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  const { otp } = await startSignup(app, mailer, db);
  const verified = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp });
  const token = verified.body.data.verificationToken;

  const cases = [
    ['short1!', 400, 'min_length'],
    ['NoNumber!', 400, 'number'],
    ['nonumber1', 400, 'special_character'],
    ['NoSpecial1', 400, 'special_character'],
    ['Has Space1!', 400, 'no_spaces'],
    ['lowercase1!', 400, 'uppercase'],
  ];

  for (const [password, status, errorCode] of cases) {
    const response = await request(app)
      .post('/api/auth/create-password')
      .send({ verificationToken: token, password, confirmPassword: password });

    assert.equal(response.status, status, password);
    assert.equal(response.body.error.code, 'WEAK_PASSWORD');
    assert.ok(
      response.body.error.details.requirements.some((item) => item.code === errorCode),
      `${password} should trigger ${errorCode}`,
    );
  }

  const mismatch = await request(app)
    .post('/api/auth/create-password')
    .send({ verificationToken: token, password: 'GoodPass1!', confirmPassword: 'GoodPass2!' });

  assert.equal(mismatch.status, 400);
  assert.equal(mismatch.body.error.code, 'PASSWORD_MISMATCH');
});

test('rejects an expired OTP', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  const { otp } = await startSignup(app, mailer, db);
  db.prepare('UPDATE otp_codes SET expires_at = ?').run(Date.now() - 1000);

  const response = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp });

  assert.equal(response.status, 400);
  assert.equal(response.body.error.code, 'OTP_EXPIRED');
});

test('locks the OTP after the maximum number of wrong attempts', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  const { otp } = await startSignup(app, mailer, db);
  const wrongOtp = otp === '111111' ? '222222' : '111111';

  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const response = await request(app)
      .post('/api/auth/verify-otp')
      .send({ email: 'user@gmail.com', otp: wrongOtp });

    if (attempt < 5) {
      assert.equal(response.status, 400);
      assert.equal(response.body.error.details.attemptsRemaining, 5 - attempt);
    } else {
      assert.equal(response.status, 429);
      assert.equal(response.body.error.code, 'OTP_ATTEMPTS_EXCEEDED');
    }
  }

  const correctAfterLock = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp });

  assert.equal(correctAfterLock.status, 400);
  assert.equal(correctAfterLock.body.error.code, 'OTP_INVALID_OR_EXPIRED');
});

test('enforces OTP resend cooldown', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  await startSignup(app, mailer, db);

  const response = await request(app)
    .post('/api/auth/request-otp')
    .send({ email: 'user@gmail.com' });

  assert.equal(response.status, 429);
  assert.equal(response.body.error.code, 'OTP_RESEND_TOO_SOON');
  assert.ok(response.body.error.details.retryAfterSeconds > 0);
});

test('returns an error when email delivery fails and allows a retry', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  mailer.shouldFail = true;
  const failed = await request(app)
    .post('/api/auth/request-otp')
    .send({ email: 'user@gmail.com' });

  assert.equal(failed.status, 502);
  assert.equal(failed.body.error.code, 'EMAIL_SEND_FAILED');
  assert.equal(db.prepare('SELECT COUNT(*) AS count FROM otp_codes').get().count, 0);

  mailer.shouldFail = false;
  const retried = await request(app)
    .post('/api/auth/request-otp')
    .send({ email: 'user@gmail.com' });

  assert.equal(retried.status, 200);
});

test('does not expose internal errors for unknown JSON fields', async (t) => {
  const { app, db, mailer } = createTestContext();
  t.after(() => db.close());

  const { otp } = await startSignup(app, mailer, db);
  const verified = await request(app)
    .post('/api/auth/verify-otp')
    .send({ email: 'user@gmail.com', otp, extra: 'ignored' });
  assert.equal(verified.status, 200);

  const missing = await request(app)
    .post('/api/auth/create-password')
    .send({ verificationToken: verified.body.data.verificationToken });
  assert.equal(missing.status, 400);
  assert.equal(missing.body.error.code, 'INVALID_REQUEST');
});

test('requires a valid bearer token for protected endpoints', async (t) => {
  const { app, db } = createTestContext();
  t.after(() => db.close());

  const missing = await request(app).get('/api/auth/me');
  assert.equal(missing.status, 401);
  assert.equal(missing.body.error.code, 'UNAUTHORIZED');

  const invalid = await request(app)
    .get('/api/auth/me')
    .set('Authorization', 'Bearer not-a-real-session-token-value');
  assert.equal(invalid.status, 401);
  assert.equal(invalid.body.error.code, 'SESSION_INVALID');
});

test('only allows browser requests from configured CORS origins', async (t) => {
  const { app, db } = createTestContext();
  t.after(() => db.close());

  const allowed = await request(app)
    .get('/api/health')
    .set('Origin', 'http://localhost:5173');
  assert.equal(allowed.headers['access-control-allow-origin'], 'http://localhost:5173');

  const blocked = await request(app)
    .get('/api/health')
    .set('Origin', 'http://evil.example');
  assert.equal(blocked.headers['access-control-allow-origin'], undefined);
});

test('rejects malformed JSON with the standard error shape', async (t) => {
  const { app, db } = createTestContext();
  t.after(() => db.close());

  const response = await request(app)
    .post('/api/auth/request-otp')
    .set('Content-Type', 'application/json')
    .send('{"email":');

  assert.equal(response.status, 400);
  assert.equal(response.body.ok, false);
  assert.equal(response.body.error.code, 'INVALID_JSON');
});
