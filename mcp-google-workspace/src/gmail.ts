import { google, gmail_v1 } from 'googleapis';
import { getAuthClient } from './auth';

export async function sendEmail(
  to: string | string[],
  subject: string,
  body: string,
  cc?: string[],
  bcc?: string[],
  bodyHtml?: string,
  draft: boolean = false
) {
  const authClient = await getAuthClient();
  const gmail = google.gmail({ version: 'v1', auth: authClient });

  // Format email addresses
  const toStr = Array.isArray(to) ? to.join(', ') : to;
  const ccStr = cc ? (Array.isArray(cc) ? cc.join(', ') : cc) : '';
  const bccStr = bcc ? (Array.isArray(bcc) ? bcc.join(', ') : bcc) : '';

  // Construct MIME message
  const boundary = 'foo_bar_baz';
  let messageParts = [
    `To: ${toStr}`,
    `Subject: ${subject}`,
    `MIME-Version: 1.0`,
    `Content-Type: multipart/alternative; boundary="${boundary}"`,
    '',
    `--${boundary}`,
    `Content-Type: text/plain; charset="UTF-8"`,
    '',
    body,
  ];

  if (ccStr) messageParts.splice(1, 0, `Cc: ${ccStr}`);
  if (bccStr) messageParts.splice(2, 0, `Bcc: ${bccStr}`);

  if (bodyHtml) {
    messageParts = messageParts.concat([
      '',
      `--${boundary}`,
      `Content-Type: text/html; charset="UTF-8"`,
      '',
      bodyHtml,
    ]);
  }

  messageParts.push('', `--${boundary}--`);

  const messageStr = messageParts.join('\n');
  const encodedMessage = Buffer.from(messageStr)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');

  try {
    if (draft) {
      const res = await gmail.users.drafts.create({
        userId: 'me',
        requestBody: {
          message: {
            raw: encodedMessage,
          },
        },
      });
      return {
        success: true,
        messageId: res.data.id,
        threadId: res.data.message?.threadId,
        timestamp: new Date().toISOString(),
      };
    } else {
      const res = await gmail.users.messages.send({
        userId: 'me',
        requestBody: {
          raw: encodedMessage,
        },
      });
      return {
        success: true,
        messageId: res.data.id,
        threadId: res.data.threadId,
        timestamp: new Date().toISOString(),
      };
    }
  } catch (error: any) {
    console.error('Error in Gmail operation:', error);
    return {
      success: false,
      error: error.message || 'Unknown error occurred',
      timestamp: new Date().toISOString(),
    };
  }
}
