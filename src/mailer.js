import nodemailer from 'nodemailer';

/*
 * Creates the SMTP mailer and the OTP email content.
 * Change the email design or wording in buildOtpEmail().
 * Change SMTP behavior in createMailer().
 */

function escapeHtml(value) {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character],
  );
}

function buildOtpEmail({ appName, otp, expiresInMinutes }) {
  const safeAppName = escapeHtml(appName);
  const subject = `Your ${appName} verification code`;

  const text = [
    `Your ${appName} verification code is: ${otp}`,
    '',
    `Enter this code on the verification page. It expires in ${expiresInMinutes} minutes.`,
    '',
    "If you didn't request this code, you can safely ignore this email.",
    '',
    `— ${appName}`,
  ].join('\n');

  const html = `<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f4f6f8;font-family:Arial,Helvetica,sans-serif;color:#1f2937;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Your verification code is ${otp}. It expires in ${expiresInMinutes} minutes.</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f6f8;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#ffffff;border-radius:10px;padding:32px;">
            <tr><td style="font-size:20px;font-weight:700;padding-bottom:24px;">${safeAppName}</td></tr>
            <tr><td style="font-size:16px;line-height:24px;">Here is your email verification code:</td></tr>
            <tr>
              <td style="padding:24px 0;">
                <div style="font-size:36px;line-height:44px;font-weight:700;letter-spacing:8px;color:#111827;">${otp}</div>
              </td>
            </tr>
            <tr>
              <td style="font-size:15px;line-height:23px;color:#4b5563;">
                Enter this code on the verification page. It expires in ${expiresInMinutes} minutes.
              </td>
            </tr>
            <tr>
              <td style="font-size:14px;line-height:22px;color:#6b7280;padding-top:24px;border-top:1px solid #e5e7eb;">
                If you didn't request this code, you can safely ignore this email.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>`;

  return { subject, text, html };
}

export function createMailer(config) {
  const { mail, appName } = config;

  if (!mail.host) {
    throw new Error('SMTP_HOST is required. Configure an SMTP provider (see README.md).');
  }
  if (!mail.from) {
    throw new Error('MAIL_FROM is required. Use a sender address verified by your email provider.');
  }
  if (mail.from.includes('\r') || mail.from.includes('\n')) {
    throw new Error('MAIL_FROM must not contain line breaks.');
  }

  const useOAuth2 = mail.authType === 'oauth2';

  if (useOAuth2) {
    if (!mail.user) {
      throw new Error('SMTP_USER is required for OAuth2. Use the Gmail address.');
    }
    if (!mail.oauth2?.clientId || !mail.oauth2?.clientSecret || !mail.oauth2?.refreshToken) {
      throw new Error(
        'SMTP_OAUTH_CLIENT_ID, SMTP_OAUTH_CLIENT_SECRET and SMTP_OAUTH_REFRESH_TOKEN ' +
          'are required when SMTP_AUTH_TYPE=oauth2.',
      );
    }
  } else if (Boolean(mail.user) !== Boolean(mail.pass)) {
    throw new Error('SMTP_USER and SMTP_PASS must be configured together.');
  }

  const transportOptions = {
    host: mail.host,
    port: mail.port,
    secure: mail.secure,
    requireTLS: mail.requireTls,
    pool: true,
    maxConnections: 2,
    maxMessages: 50,
    connectionTimeout: mail.timeoutMs,
    greetingTimeout: mail.timeoutMs,
    socketTimeout: mail.timeoutMs,
    disableFileAccess: true,
    disableUrlAccess: true,
    logger: false,
    debug: false,
    tls: { minVersion: 'TLSv1.2' },
  };

  if (useOAuth2) {
    transportOptions.auth = {
      type: 'OAuth2',
      user: mail.user,
      clientId: mail.oauth2.clientId,
      clientSecret: mail.oauth2.clientSecret,
      refreshToken: mail.oauth2.refreshToken,
    };
  } else if (mail.user) {
    transportOptions.auth = { user: mail.user, pass: mail.pass };
  }

  const transporter = nodemailer.createTransport(transportOptions);

  return {
    async verify() {
      return transporter.verify();
    },

    async sendOtpEmail({ to, otp, expiresInMinutes }) {
      const content = buildOtpEmail({ appName, otp, expiresInMinutes });

      return transporter.sendMail({
        from: mail.from,
        to,
        replyTo: mail.replyTo,
        subject: content.subject,
        text: content.text,
        html: content.html,
        headers: {
          'X-Auto-Response-Suppress': 'All',
        },
      });
    },
  };
}
