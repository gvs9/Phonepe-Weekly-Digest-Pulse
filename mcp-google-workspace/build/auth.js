"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.SCOPES = void 0;
exports.getAuthClient = getAuthClient;
const googleapis_1 = require("googleapis");
const dotenv_1 = __importDefault(require("dotenv"));
const fs_1 = __importDefault(require("fs"));
dotenv_1.default.config();
// The Google APIs require specific scopes
exports.SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/documents',
];
/**
 * Returns an authenticated OAuth2 client using a Service Account or OAuth credentials.
 * The implementation prefers `GOOGLE_APPLICATION_CREDENTIALS` for Service Accounts.
 */
async function getAuthClient() {
    // If GOOGLE_APPLICATION_CREDENTIALS is set, google.auth.getClient automatically picks it up
    if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
        try {
            const auth = new googleapis_1.google.auth.GoogleAuth({
                scopes: exports.SCOPES,
            });
            const authClient = await auth.getClient();
            return authClient;
        }
        catch (error) {
            console.error('Error authenticating with GOOGLE_APPLICATION_CREDENTIALS', error);
            throw error;
        }
    }
    // Fallback to expecting credentials.json path from an environment variable (for OAuth2 user flow if needed)
    const credPath = process.env.GOOGLE_OAUTH_CREDENTIALS_PATH;
    if (credPath && fs_1.default.existsSync(credPath)) {
        console.warn('OAuth2 user flow not fully implemented in this stub. Falling back to application default credentials.');
    }
    // Last resort: Application Default Credentials
    const auth = new googleapis_1.google.auth.GoogleAuth({
        scopes: exports.SCOPES,
    });
    return auth.getClient();
}
