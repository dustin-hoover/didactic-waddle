/**
 * MCP server stub: state-license-board
 *
 * Placeholder tool returns not-implemented until a real data contract with the
 * beachhead state's licensing board exists. Fail-closed by design: callers must
 * treat an unverified license as disqualifying, never as a pass.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new Server(
  { name: "state-license-board", version: "0.0.1" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler("tools/list", async () => ({
  tools: [
    {
      name: "verify_license",
      description:
        "Verify a trade license against the state board of record. STUB.",
      inputSchema: {
        type: "object",
        properties: {
          license_number: { type: "string" },
          state: { type: "string" },
        },
        required: ["license_number", "state"],
      },
    },
  ],
}));

server.setRequestHandler("tools/call", async () => ({
  content: [
    {
      type: "text",
      text: JSON.stringify({ status: "not-implemented", contract_needed: true }),
    },
  ],
}));

const transport = new StdioServerTransport();
await server.connect(transport);
