// subagent_pipeline.ts
// Demonstrates TappsMCP subagent registration via Agent SDK agents parameter

import {
  query,
  type ClaudeCodeOptions,
  type AgentDefinition,
} from "@anthropic-ai/claude-code";

// Define a TappsMCP quality reviewer subagent
const tappsReviewerAgent: AgentDefinition = {
  name: "tapps-reviewer",
  description:
    "Use proactively to review code quality and run security scans after editing Python files.",
  systemPrompt: `You are a TappsMCP quality reviewer. When invoked:
1. Call mcp__tapps-mcp__tapps_quick_check on each changed file
2. If any file scores below 70, call mcp__tapps-mcp__tapps_score_file
3. Summarize findings concisely`,
  tools: ["Read", "Glob", "Grep"],
  model: "sonnet",
};

async function runWithReviewerAgent(task: string): Promise<void> {
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
    // Register the reviewer subagent
    agents: [tappsReviewerAgent],
    maxTurns: 10,
  };

  for await (const message of query({ prompt: task, options })) {
    console.log(message);
  }
}

runWithReviewerAgent(
  "Review the quality of all Python files changed in the last commit."
).catch(console.error);
