# Google Workspace MCP Server

This is a Model Context Protocol (MCP) server that provides AI agents with standardized access to Gmail and Google Docs capabilities.

## Features

- **Gmail Integration:**
  - Send emails (plain text or HTML)
  - Create email drafts
- **Google Docs Integration:**
  - Append content (plain text or HTML) to the end of a document
  - Batch append multiple sections sequentially
- **Authentication:**
  - Supports Google OAuth 2.0 (Service Accounts or Application Default Credentials)

## Prerequisites

- Node.js (v18 or higher recommended, but supports v14 fallback)
- A Google Cloud Project with the following APIs enabled:
  - Gmail API
  - Google Docs API
- Valid OAuth 2.0 Credentials (Service Account Key `credentials.json`)

## Installation

```bash
# Clone the repository and install dependencies
npm install

# Compile the TypeScript code
npm run build
```

## Configuration

Set up your authentication by defining one of the following environment variables. The easiest way is to create a `.env` file in the root directory:

```env
# Preferred: Path to your Google Service Account credentials JSON file
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/credentials.json
```

## Running the Server

Start the MCP server using standard I/O (StdioServerTransport):

```bash
npm start
```

## Provided Tools

The server exposes the following MCP tools:

1. `gmail_send_email`
   - `to` (string | array)
   - `subject` (string)
   - `body` (string)
   - `cc` (array, optional)
   - `bcc` (array, optional)
   - `bodyHtml` (string, optional)
   - `draft` (boolean, optional, defaults to false)

2. `gmail_draft_email`
   - Wrapper for `gmail_send_email` forcing `draft: true`

3. `docs_append_content`
   - `documentId` (string)
   - `content` (string)
   - `heading` (string, optional)
   - `appendNewline` (boolean, optional, defaults to true)

4. `docs_append_multiple`
   - `documentId` (string)
   - `items` (array of `{ content, heading }`)

## MCP Client Configuration

To connect this server from an MCP-compatible AI agent (like Claude Desktop or an MCP Python client), add the following to the client configuration:

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-google-workspace/build/index.js"]
    }
  }
}
```

## Development

Run the TypeScript compiler in watch mode for development:

```bash
npm run dev
```
