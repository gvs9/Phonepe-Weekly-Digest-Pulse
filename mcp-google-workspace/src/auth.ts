import { google } from 'googleapis';
import { OAuth2Client } from 'google-auth-library';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';

dotenv.config();

// The Google APIs require specific scopes
export const SCOPES = [
  'https://www.googleapis.com/auth/gmail.send',
  'https://www.googleapis.com/auth/gmail.compose',
  'https://www.googleapis.com/auth/documents',
];

/**
 * Returns an authenticated OAuth2 client using a Service Account or OAuth credentials.
 * The implementation prefers `GOOGLE_APPLICATION_CREDENTIALS` for Service Accounts.
 */
export async function getAuthClient(): Promise<OAuth2Client | any> {
  // If GOOGLE_APPLICATION_CREDENTIALS is set, google.auth.getClient automatically picks it up
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    try {
      const auth = new google.auth.GoogleAuth({
        scopes: SCOPES,
      });
      const authClient = await auth.getClient();
      return authClient;
    } catch (error) {
      console.error('Error authenticating with GOOGLE_APPLICATION_CREDENTIALS', error);
      throw error;
    }
  }

  // Fallback to expecting credentials.json path from an environment variable (for OAuth2 user flow if needed)
  const credPath = process.env.GOOGLE_OAUTH_CREDENTIALS_PATH;
  if (credPath && fs.existsSync(credPath)) {
    console.warn('OAuth2 user flow not fully implemented in this stub. Falling back to application default credentials.');
  }

  // Last resort: Application Default Credentials
  const auth = new google.auth.GoogleAuth({
    scopes: SCOPES,
  });
  return auth.getClient();
}
