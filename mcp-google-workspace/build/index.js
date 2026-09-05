"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const index_js_1 = require("@modelcontextprotocol/sdk/server/index.js");
const stdio_js_1 = require("@modelcontextprotocol/sdk/server/stdio.js");
const types_js_1 = require("@modelcontextprotocol/sdk/types.js");
const gmail_1 = require("./gmail");
const docs_1 = require("./docs");
const server = new index_js_1.Server({
    name: 'google-workspace-mcp',
    version: '1.0.0',
}, {
    capabilities: {
        tools: {},
    },
});
// Register Tools
server.setRequestHandler(types_js_1.ListToolsRequestSchema, async () => {
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
server.setRequestHandler(types_js_1.CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    try {
        switch (name) {
            case 'gmail_send_email': {
                if (!args || !args.to || !args.subject || !args.body) {
                    throw new Error('Missing required arguments for gmail_send_email');
                }
                const result = await (0, gmail_1.sendEmail)(args.to, args.subject, args.body, args.cc, args.bcc, args.bodyHtml, args.draft);
                return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
            }
            case 'gmail_draft_email': {
                if (!args || !args.to || !args.subject || !args.body) {
                    throw new Error('Missing required arguments for gmail_draft_email');
                }
                const result = await (0, gmail_1.sendEmail)(args.to, args.subject, args.body, args.cc, args.bcc, args.bodyHtml, true // Force draft mode
                );
                return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
            }
            case 'docs_append_content': {
                if (!args || !args.documentId || !args.content) {
                    throw new Error('Missing required arguments for docs_append_content');
                }
                const result = await (0, docs_1.appendContent)(args.documentId, args.content, args.heading, args.appendNewline);
                return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
            }
            case 'docs_append_multiple': {
                if (!args || !args.documentId || !args.items) {
                    throw new Error('Missing required arguments for docs_append_multiple');
                }
                const result = await (0, docs_1.appendMultiple)(args.documentId, args.items);
                return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
            }
            default:
                throw new Error(`Unknown tool: ${name}`);
        }
    }
    catch (error) {
        console.error(`Error executing tool ${name}:`, error);
        return {
            content: [{ type: 'text', text: `Error: ${error.message}` }],
            isError: true,
        };
    }
});
// Start Server
async function main() {
    const transport = new stdio_js_1.StdioServerTransport();
    await server.connect(transport);
    console.error('Google Workspace MCP server running on stdio');
}
main().catch((error) => {
    console.error('Fatal error in main():', error);
    process.exit(1);
});
