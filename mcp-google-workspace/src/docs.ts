import { google } from 'googleapis';
import { getAuthClient } from './auth';

export async function appendContent(
  documentId: string,
  content: string,
  heading?: string,
  appendNewline: boolean = true
) {
  const authClient = await getAuthClient();
  const docs = google.docs({ version: 'v1', auth: authClient });

  try {
    const requests: any[] = [];
    
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
    const insertRequests: any[] = [
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
  } catch (error: any) {
    console.error('Error in Docs operation:', error);
    return {
      success: false,
      error: error.message || 'Unknown error occurred',
      timestamp: new Date().toISOString(),
    };
  }
}

export async function appendMultiple(
  documentId: string,
  items: Array<{ content: string; heading?: string }>
) {
  let itemsAppended = 0;
  let failedItems: any[] = [];
  
  for (const item of items) {
    const result = await appendContent(documentId, item.content, item.heading, true);
    if (result.success) {
      itemsAppended++;
    } else {
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
