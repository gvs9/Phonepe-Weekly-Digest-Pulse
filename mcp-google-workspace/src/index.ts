import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

import { sendEmail } from './gmail';
import { appendContent, appendMultiple } from './docs';

const server = new Server(
  {
    name: 'google-workspace-mcp',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Register Tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: 'gmail_send_email',
        description: 'Send an email via Gmail',
        inputSchema: {
          type: 'object',
          properties: {
            to: { type: ['string', 'array'], description: 'Recipient email address(es)' },
            subject: { type: 'string', description: 'Email subject line' },
            body: { type: 'string', description: 'Email body in plain text' },
            cc: { type: 'array', items: { type: 'string' }, description: 'CC recipients' },
            bcc: { type: 'array', items: { type: 'string' }, description: 'BCC recipients' },
            bodyHtml: { type: 'string', description: 'Email body in HTML format (optional)' },
            draft: { type: 'boolean', description: 'Save as draft instead of sending', default: false },
          },
          required: ['to', 'subject', 'body'],
        },
      },
      {
        name: 'gmail_draft_email',
        description: 'Draft an email via Gmail',
        inputSchema: {
          type: 'object',
          properties: {
            to: { type: ['string', 'array'], description: 'Recipient email address(es)' },
            subject: { type: 'string', description: 'Email subject line' },
            body: { type: 'string', description: 'Email body in plain text' },
            cc: { type: 'array', items: { type: 'string' }, description: 'CC recipients' },
            bcc: { type: 'array', items: { type: 'string' }, description: 'BCC recipients' },
            bodyHtml: { type: 'string', description: 'Email body in HTML format (optional)' },
          },
          required: ['to', 'subject', 'body'],
        },
      },
      {
        name: 'docs_append_content',
        description: 'Append content to a Google Doc',
        inputSchema: {
          type: 'object',
          properties: {
            documentId: { type: 'string', description: 'Google Docs document ID' },
            content: { type: 'string', description: 'Content to append' },
            heading: { type: 'string', description: 'Optional section heading' },
            appendNewline: { type: 'boolean', default: true },
          },
          required: ['documentId', 'content'],
        },
      },
      {
        name: 'docs_append_multiple',
        description: 'Append multiple items to a Google Doc sequentially',
        inputSchema: {
          type: 'object',
          properties: {
            documentId: { type: 'string', description: 'Google Docs document ID' },
            items: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  content: { type: 'string' },
                  heading: { type: 'string' },
                },
                required: ['content'],
              },
            },
          },
          required: ['documentId', 'items'],
        },
      },
    ],
  };
});

// Handle Tool Execution
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'gmail_send_email': {
        if (!args || !args.to || !args.subject || !args.body) {
          throw new Error('Missing required arguments for gmail_send_email');
        }
        const result = await sendEmail(
          args.to as string | string[],
          args.subject as string,
          args.body as string,
          args.cc as string[],
          args.bcc as string[],
          args.bodyHtml as string,
          args.draft as boolean | undefined
        );
        return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
      }
      
      case 'gmail_draft_email': {
        if (!args || !args.to || !args.subject || !args.body) {
          throw new Error('Missing required arguments for gmail_draft_email');
        }
        const result = await sendEmail(
          args.to as string | string[],
          args.subject as string,
          args.body as string,
          args.cc as string[],
          args.bcc as string[],
          args.bodyHtml as string,
          true // Force draft mode
        );
        return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
      }

      case 'docs_append_content': {
        if (!args || !args.documentId || !args.content) {
          throw new Error('Missing required arguments for docs_append_content');
        }
        const result = await appendContent(
          args.documentId as string,
          args.content as string,
          args.heading as string,
          args.appendNewline as boolean
        );
        return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
      }

      case 'docs_append_multiple': {
        if (!args || !args.documentId || !args.items) {
          throw new Error('Missing required arguments for docs_append_multiple');
        }
        const result = await appendMultiple(
          args.documentId as string,
          args.items as any[]
        );
        return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error: any) {
    console.error(`Error executing tool ${name}:`, error);
    return {
      content: [{ type: 'text', text: `Error: ${error.message}` }],
      isError: true,
    };
  }
});

// Start Server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Google Workspace MCP server running on stdio');
}

main().catch((error) => {
  console.error('Fatal error in main():', error);
  process.exit(1);
});
