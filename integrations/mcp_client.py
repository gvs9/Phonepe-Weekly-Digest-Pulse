"""
integrations/mcp_client.py
--------------------------
Phase 5 & 6 — Connects to remote MCP server via SSE to interact with Google Docs and Gmail.
"""

import asyncio
import logging
from typing import Optional

from pulse import PulseNote

logger = logging.getLogger(__name__)

async def _publish_to_google_doc_async(pulse: PulseNote, config: dict) -> Optional[str]:
    try:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession
    except ImportError:
        logger.error("mcp package is not installed.")
        return None

    mcp_url = config.get("mcp_server_url")
    doc_id = config.get("google_doc_id")
    
    if not mcp_url:
        logger.warning("mcp_server_url not configured. Skipping Google Docs publish.")
        return None
    if not doc_id:
        logger.warning("google_doc_id not configured. Skipping Google Docs publish.")
        return None

    try:
        async with sse_client(mcp_url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                
                logger.info(f"Connected to MCP Server at {mcp_url}. Publishing to doc {doc_id}...")
                
                result = await session.call_tool("docs_append_content", arguments={
                    "documentId": doc_id,
                    "content": pulse.as_markdown(),
                    "heading": f"Weekly Pulse - {pulse.week_ending}"
                })
                
                if result.is_error:
                    logger.error(f"Failed to append to Google Doc: {result.content}")
                    return None
                    
                logger.info("Successfully published to Google Doc.")
                return f"https://docs.google.com/document/d/{doc_id}/edit"
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"MCP Server error during docs_append_content: {e}")
        return None

def publish_to_google_doc(pulse: PulseNote, config: dict) -> Optional[str]:
    """
    Connects to the MCP server via SSE and appends the markdown pulse to a Google Doc.
    Returns the Google Doc URL on success, or None on failure.
    """
    return asyncio.run(_publish_to_google_doc_async(pulse, config))

async def _create_gmail_draft_async(pulse: PulseNote, doc_url: str, config: dict) -> Optional[str]:
    mcp_url = config.get("mcp_server_url")
    recipient = config.get("gmail_recipient")

    if not mcp_url:
        logger.warning("mcp_server_url not configured. Skipping Gmail draft.")
        return None
    if not recipient:
        logger.warning("gmail_recipient not configured. Skipping Gmail draft.")
        return None

    subject = pulse.email_subject or f"Weekly App Feedback Pulse — Week ending {pulse.week_ending}"
    
    plain_text = f"{pulse.email_intro}\n\n{pulse.as_plain_text()}\n\n"
    if doc_url:
        plain_text += f"View full pulse in Google Docs: {doc_url}\n"

    # Minimal HTML format
    html_body = f"<p>{pulse.email_intro}</p><pre>{pulse.as_plain_text()}</pre>"
    if doc_url:
        html_body += f"<br><p><strong>View full pulse in Google Docs:</strong> <a href='{doc_url}'>{doc_url}</a></p>"

    try:
        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession
        
        async with sse_client(mcp_url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                
                logger.info(f"Connected to MCP Server. Creating Gmail draft for {recipient}...")
                
                result = await session.call_tool("gmail_send_email", arguments={
                    "to": recipient,
                    "subject": subject,
                    "body": plain_text,
                    "bodyHtml": html_body,
                    "draft": True
                })
                
                if result.is_error:
                    logger.error(f"Failed to create Gmail draft: {result.content}")
                    return None
                    
                logger.info("Successfully created Gmail draft.")
                # The result content is usually a JSON string containing the response from Gmail
                # For simplicity, we just return a success message with the response payload
                return str(result.content[0].text if result.content else "Draft Created")
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"MCP Server error during gmail_send_email (draft): {e}")
        return None

def create_gmail_draft_mcp(pulse: PulseNote, doc_url: str, config: dict) -> Optional[str]:
    """
    Connects to the MCP server via SSE and creates a Gmail draft.
    Returns the Draft confirmation string on success, or None on failure.
    """
    return asyncio.run(_create_gmail_draft_async(pulse, doc_url, config))

