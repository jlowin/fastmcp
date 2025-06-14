import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

// WAHA MCP PLUS - Premium WhatsApp Automation Configuration
export const configSchema = z.object({
  debug: z.boolean().default(false).describe("Enable debug logging"),
  wahaUrl: z.string().default("http://localhost:3000").describe("WAHA Server URL"),
  apiKey: z.string().optional().describe("WAHA API Key for authentication"),
  maxSessions: z.number().default(10).describe("Maximum concurrent sessions"),
  enableAnalytics: z.boolean().default(true).describe("Enable analytics tracking"),
  enableAutoReply: z.boolean().default(true).describe("Enable auto-reply feature"),
});

export default function createStatelessServer({
  config,
}: {
  config: z.infer<typeof configSchema>;
}) {
  const server = new McpServer({
    name: "WAHA MCP PLUS - Premium WhatsApp Automation",
    version: "1.0.0-plus",
  });

  // =============================================
  // SESSION MANAGEMENT TOOLS
  // =============================================

  server.tool(
    "start_session",
    "Start a new WhatsApp session",
    {
      session: z.string().describe("Session name/ID"),
      webhook: z.string().optional().describe("Webhook URL for events"),
      config: z.object({
        proxy: z.string().optional(),
        headless: z.boolean().default(true),
      }).optional(),
    },
    async ({ session, webhook, config: sessionConfig }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sessions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
          body: JSON.stringify({
            name: session,
            webhook,
            config: sessionConfig,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to start session: ${response.statusText}`);
        }

        const result = await response.json();
        return {
          content: [{ 
            type: "text", 
            text: `✅ Session '${session}' started successfully!\n\nStatus: ${result.status}\nDetails: ${JSON.stringify(result, null, 2)}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error starting session: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "stop_session",
    "Stop an active WhatsApp session",
    {
      session: z.string().describe("Session name/ID to stop"),
      logout: z.boolean().default(false).describe("Logout before stopping"),
    },
    async ({ session, logout }) => {
      try {
        const url = `${config.wahaUrl}/api/sessions/${session}/stop${logout ? '?logout=true' : ''}`;
        const response = await fetch(url, {
          method: 'DELETE',
          headers: {
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to stop session: ${response.statusText}`);
        }

        return {
          content: [{ 
            type: "text", 
            text: `✅ Session '${session}' stopped successfully!${logout ? ' (logged out)' : ''}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error stopping session: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "list_sessions",
    "List all active WhatsApp sessions",
    {},
    async () => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sessions`, {
          headers: {
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to list sessions: ${response.statusText}`);
        }

        const sessions = await response.json();
        const sessionList = sessions.map((s: any) => 
          `📱 ${s.name} - Status: ${s.status} - Engine: ${s.config?.engine || 'webjs'}`
        ).join('\n');

        return {
          content: [{ 
            type: "text", 
            text: `🔄 Active Sessions (${sessions.length}):\n\n${sessionList || 'No active sessions'}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error listing sessions: ${error.message}` 
          }],
        };
      }
    }
  );

  // =============================================
  // MESSAGING TOOLS
  // =============================================

  server.tool(
    "send_message",
    "Send a text message via WhatsApp",
    {
      session: z.string().describe("Session name/ID"),
      chatId: z.string().describe("Chat ID (phone number with @c.us or group ID)"),
      text: z.string().describe("Message text"),
      mentions: z.array(z.string()).optional().describe("Phone numbers to mention"),
    },
    async ({ session, chatId, text, mentions }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sendText`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
          body: JSON.stringify({
            session,
            chatId,
            text,
            mentions,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to send message: ${response.statusText}`);
        }

        const result = await response.json();
        return {
          content: [{ 
            type: "text", 
            text: `✅ Message sent successfully!\n\nMessage ID: ${result.id}\nTo: ${chatId}\nText: "${text}"` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error sending message: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "send_image",
    "Send an image via WhatsApp",
    {
      session: z.string().describe("Session name/ID"),
      chatId: z.string().describe("Chat ID"),
      file: z.object({
        mimetype: z.string(),
        filename: z.string(),
        data: z.string().describe("Base64 encoded image data"),
      }),
      caption: z.string().optional().describe("Image caption"),
    },
    async ({ session, chatId, file, caption }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sendImage`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
          body: JSON.stringify({
            session,
            chatId,
            file,
            caption,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to send image: ${response.statusText}`);
        }

        const result = await response.json();
        return {
          content: [{ 
            type: "text", 
            text: `🖼️ Image sent successfully!\n\nMessage ID: ${result.id}\nTo: ${chatId}\nFilename: ${file.filename}${caption ? `\nCaption: "${caption}"` : ''}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error sending image: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "send_document",
    "Send a document file via WhatsApp",
    {
      session: z.string().describe("Session name/ID"),
      chatId: z.string().describe("Chat ID"),
      file: z.object({
        mimetype: z.string(),
        filename: z.string(),
        data: z.string().describe("Base64 encoded file data"),
      }),
      caption: z.string().optional().describe("Document caption"),
    },
    async ({ session, chatId, file, caption }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sendFile`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
          body: JSON.stringify({
            session,
            chatId,
            file,
            caption,
          }),
        });

        if (!response.ok) {
          throw new Error(`Failed to send document: ${response.statusText}`);
        }

        const result = await response.json();
        return {
          content: [{ 
            type: "text", 
            text: `📄 Document sent successfully!\n\nMessage ID: ${result.id}\nTo: ${chatId}\nFilename: ${file.filename}${caption ? `\nCaption: "${caption}"` : ''}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error sending document: ${error.message}` 
          }],
        };
      }
    }
  );

  // =============================================
  // CONTACT & CHAT MANAGEMENT
  // =============================================

  server.tool(
    "get_contacts",
    "Get all contacts from a session",
    {
      session: z.string().describe("Session name/ID"),
    },
    async ({ session }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/contacts?session=${session}`, {
          headers: {
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to get contacts: ${response.statusText}`);
        }

        const contacts = await response.json();
        const contactList = contacts.slice(0, 10).map((c: any) => 
          `👤 ${c.name || c.pushname || 'Unknown'} (${c.id})`
        ).join('\n');

        return {
          content: [{ 
            type: "text", 
            text: `📇 Contacts (showing first 10 of ${contacts.length}):\n\n${contactList}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error getting contacts: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "get_chats",
    "Get all chats from a session",
    {
      session: z.string().describe("Session name/ID"),
      limit: z.number().default(20).describe("Maximum number of chats to return"),
    },
    async ({ session, limit }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/chats?session=${session}&limit=${limit}`, {
          headers: {
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to get chats: ${response.statusText}`);
        }

        const chats = await response.json();
        const chatList = chats.map((c: any) => 
          `💬 ${c.name || 'Unknown'} (${c.id}) - ${c.unreadCount || 0} unread`
        ).join('\n');

        return {
          content: [{ 
            type: "text", 
            text: `💬 Recent Chats (${chats.length}):\n\n${chatList}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error getting chats: ${error.message}` 
          }],
        };
      }
    }
  );

  // =============================================
  // MESSAGE HISTORY & ANALYTICS
  // =============================================

  server.tool(
    "get_messages",
    "Get message history from a chat",
    {
      session: z.string().describe("Session name/ID"),
      chatId: z.string().describe("Chat ID"),
      limit: z.number().default(10).describe("Number of messages to retrieve"),
      downloadMedia: z.boolean().default(false).describe("Download media files"),
    },
    async ({ session, chatId, limit, downloadMedia }) => {
      try {
        const response = await fetch(
          `${config.wahaUrl}/api/messages?session=${session}&chatId=${chatId}&limit=${limit}&downloadMedia=${downloadMedia}`,
          {
            headers: {
              ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
            },
          }
        );

        if (!response.ok) {
          throw new Error(`Failed to get messages: ${response.statusText}`);
        }

        const messages = await response.json();
        const messageList = messages.map((m: any) => 
          `📨 ${m.from}: ${m.body || '[Media]'} (${new Date(m.timestamp * 1000).toLocaleString()})`
        ).join('\n');

        return {
          content: [{ 
            type: "text", 
            text: `📨 Messages from ${chatId} (${messages.length}):\n\n${messageList}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error getting messages: ${error.message}` 
          }],
        };
      }
    }
  );

  // =============================================
  // PREMIUM AUTOMATION TOOLS
  // =============================================

  server.tool(
    "create_broadcast",
    "Create and send a broadcast message to multiple contacts",
    {
      session: z.string().describe("Session name/ID"),
      contacts: z.array(z.string()).describe("Array of contact IDs"),
      message: z.string().describe("Broadcast message"),
      delayBetween: z.number().default(1000).describe("Delay between messages (ms)"),
    },
    async ({ session, contacts, message, delayBetween }) => {
      try {
        const results = [];
        for (const contact of contacts) {
          try {
            const response = await fetch(`${config.wahaUrl}/api/sendText`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
              },
              body: JSON.stringify({
                session,
                chatId: contact,
                text: message,
              }),
            });

            if (response.ok) {
              results.push(`✅ ${contact}: sent`);
            } else {
              results.push(`❌ ${contact}: failed`);
            }

            // Delay between messages
            await new Promise(resolve => setTimeout(resolve, delayBetween));
          } catch (error) {
            results.push(`❌ ${contact}: error - ${error.message}`);
          }
        }

        return {
          content: [{ 
            type: "text", 
            text: `📢 Broadcast completed!\n\nResults:\n${results.join('\n')}\n\nTotal: ${contacts.length} contacts` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error creating broadcast: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "schedule_message",
    "Schedule a message to be sent later (simulated)",
    {
      session: z.string().describe("Session name/ID"),
      chatId: z.string().describe("Chat ID"),
      message: z.string().describe("Message to schedule"),
      scheduleTime: z.string().describe("Schedule time (ISO 8601 format)"),
    },
    async ({ session, chatId, message, scheduleTime }) => {
      try {
        const scheduledDate = new Date(scheduleTime);
        const now = new Date();
        
        if (scheduledDate <= now) {
          throw new Error("Schedule time must be in the future");
        }

        // In a real implementation, this would store the message in a database
        // and use a job scheduler. For now, we'll just return a confirmation.
        const delay = scheduledDate.getTime() - now.getTime();
        
        return {
          content: [{ 
            type: "text", 
            text: `⏰ Message scheduled successfully!\n\nSession: ${session}\nTo: ${chatId}\nMessage: "${message}"\nScheduled for: ${scheduledDate.toLocaleString()}\nDelay: ${Math.round(delay / 1000 / 60)} minutes\n\n⚠️ Note: This is a simulation. In production, implement with a job scheduler.` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error scheduling message: ${error.message}` 
          }],
        };
      }
    }
  );

  // =============================================
  // WEBHOOK & STATUS TOOLS
  // =============================================

  server.tool(
    "get_webhook_status",
    "Get webhook configuration and status",
    {
      session: z.string().describe("Session name/ID"),
    },
    async ({ session }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sessions/${session}/webhook`, {
          headers: {
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to get webhook status: ${response.statusText}`);
        }

        const webhook = await response.json();
        return {
          content: [{ 
            type: "text", 
            text: `🔗 Webhook Status for '${session}':\n\n${JSON.stringify(webhook, null, 2)}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error getting webhook status: ${error.message}` 
          }],
        };
      }
    }
  );

  server.tool(
    "get_session_status",
    "Get detailed status of a WhatsApp session",
    {
      session: z.string().describe("Session name/ID"),
    },
    async ({ session }) => {
      try {
        const response = await fetch(`${config.wahaUrl}/api/sessions/${session}`, {
          headers: {
            ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
          },
        });

        if (!response.ok) {
          throw new Error(`Failed to get session status: ${response.statusText}`);
        }

        const status = await response.json();
        return {
          content: [{ 
            type: "text", 
            text: `📊 Session Status for '${session}':\n\n${JSON.stringify(status, null, 2)}` 
          }],
        };
      } catch (error) {
        return {
          content: [{ 
            type: "text", 
            text: `❌ Error getting session status: ${error.message}` 
          }],
        };
      }
    }
  );

  return server.server;
}
