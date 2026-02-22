// basic_quality_check.ts
// Prerequisites: npm install @anthropic-ai/claude-code
// ANTHROPIC_API_KEY and TAPPS_MCP_PROJECT_ROOT must be set

import { query, type ClaudeCodeOptions } from "@anthropic-ai/claude-code";

async function runQualityCheck(filePath: string): Promise<void> {
  const options: ClaudeCodeOptions = {
    // Configure TappsMCP as an MCP server
    mcpServers: {
      "tapps-mcp": {
        command: "uvx",
        args: ["tapps-mcp", "serve"],
        env: {
          TAPPS_MCP_PROJECT_ROOT:
            process.env.TAPPS_MCP_PROJECT_ROOT ?? process.cwd(),
        },
      },
    },
    // Restrict tool access to only the quick check tool
    allowedTools: ["mcp__tapps-mcp__tapps_quick_check"],
    maxTurns: 3,
  };

  for await (const message of query({
    prompt: `Run tapps_quick_check on ${filePath} and report the score and top issues.`,
    options,
  })) {
    if ("content" in message) {
      console.log(message.content);
    }
  }
}

const filePath = process.argv[2] ?? "src/main.py";
runQualityCheck(filePath).catch(console.error);
