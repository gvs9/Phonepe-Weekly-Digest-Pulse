"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.appendContent = appendContent;
exports.appendMultiple = appendMultiple;
const googleapis_1 = require("googleapis");
const auth_1 = require("./auth");
async function appendContent(documentId, content, heading, appendNewline = true) {
    const authClient = await (0, auth_1.getAuthClient)();
    const docs = googleapis_1.google.docs({ version: 'v1', auth: authClient });
    try {
        const requests = [];
        // First, append the text (and optional heading + newline)
        let textToInsert = '';
        if (heading) {
            textToInsert += heading + '\n';
        }
        textToInsert += content;
        if (appendNewline) {
            textToInsert += '\n';
        }
        requests.push({
            insertText: {
                location: {
                    index: 1, // End of document will require retrieving the doc length, but for simplicity, the API supports appending to the end if we use EndOfSegmentLocation or calculate it.
                    // Wait, Docs API insertText requires a specific index. 
                    // We must fetch the document first to find the end index.
                }
            }
        });
        // Let's retrieve the doc to get the end index
        const docMeta = await docs.documents.get({ documentId });
        const contentList = docMeta.data.body?.content;
        let endIndex = 1;
        if (contentList && contentList.length > 0) {
            const lastElement = contentList[contentList.length - 1];
            endIndex = (lastElement.endIndex || 2) - 1;
        }
        // Now insert text at endIndex
        const insertRequests = [
            {
                insertText: {
                    location: { index: endIndex },
                    text: textToInsert,
                }
            }
        ];
        // If heading is provided, format it
        if (heading) {
            insertRequests.push({
                updateParagraphStyle: {
                    range: {
                        startIndex: endIndex,
                        endIndex: endIndex + heading.length,
                    },
                    paragraphStyle: {
                        namedStyleType: 'HEADING_2',
                    },
                    fields: 'namedStyleType',
                }
            });
        }
        await docs.documents.batchUpdate({
            documentId,
            requestBody: {
                requests: insertRequests,
            }
        });
        return {
            success: true,
            documentId,
            endIndex: endIndex + textToInsert.length,
            timestamp: new Date().toISOString(),
        };
    }
    catch (error) {
        console.error('Error in Docs operation:', error);
        return {
            success: false,
            error: error.message || 'Unknown error occurred',
            timestamp: new Date().toISOString(),
        };
    }
}
async function appendMultiple(documentId, items) {
    let itemsAppended = 0;
    let failedItems = [];
    for (const item of items) {
        const result = await appendContent(documentId, item.content, item.heading, true);
        if (result.success) {
            itemsAppended++;
        }
        else {
            failedItems.push({
                item,
                error: result.error,
            });
        }
    }
    return {
        success: failedItems.length === 0,
        documentId,
        itemsAppended,
        failedItems,
        timestamp: new Date().toISOString(),
    };
}
