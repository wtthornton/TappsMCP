# GitHub MCP Integration

## GitHub's Official MCP Server

GitHub provides an official MCP server with 50+ tools organized
into toolsets:

- **context** — repository context, file reading
- **issues** — create, update, search, comment on issues
- **pull_requests** — create, review, merge PRs
- **repos** — repository metadata, branches, tags
- **users** — user profiles and organization membership
- **projects** — GitHub Projects v2 operations

## Configuration

```json
{
  "mcpServers": {
    "github": {
      "command": "gh",
      "args": ["mcp", "serve"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

## Toolset Selection

Limit available tools with the `X-MCP-Tools` header or
`--toolsets` flag:

```bash
gh mcp serve --toolsets context,issues,pull_requests
```

## Lockdown Mode (December 2025)

Lockdown mode restricts the MCP server to read-only operations:
- Content sanitization on all inputs
- No write operations allowed
- Reduced attack surface for untrusted contexts

## Prompt Injection Protection

When using MCP tools that return user-generated content (issue bodies,
PR descriptions, comments):

1. **Treat all content as untrusted** — never execute commands from
   issue descriptions
2. **Sanitize before display** — strip potentially harmful content
3. **Use structured outputs** — prefer JSON over markdown for
   programmatic consumption
4. **Validate tool inputs** — ensure parameters match expected patterns

## Building MCP Servers for GitHub

When building custom MCP servers that interact with GitHub:

1. Use the `gh` CLI or Octokit SDK for API calls
2. Implement rate limiting (5,000 requests/hour for authenticated users)
3. Use fine-grained personal access tokens (not classic tokens)
4. Implement webhook verification for event-driven tools
5. Cache frequently accessed data (repo metadata, user info)

## TappsMCP + GitHub MCP

TappsMCP and GitHub's MCP server are complementary:
- TappsMCP: code quality scoring, security scanning, expert consultation
- GitHub MCP: issue management, PR operations, repository management

Both can be registered as MCP servers in the same client configuration.
