# YouTube MCP Setup

The [YouTube MCP server](https://github.com/bendelpino/youtube-mcp) is configured for this workspace. It provides:

- **search_youtube_videos** — Search YouTube by query with customizable result count
- **get_youtube_transcript** — Extract transcripts from videos (URL or video ID)
- **analyze_youtube_content_prompt** — AI prompt template for content analysis

## API Key (required for search)

The `search_youtube_videos` tool requires a YouTube Data API v3 key. Transcripts work without it.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select an existing one
3. Enable **YouTube Data API v3**
4. Create credentials → **API Key**
5. Copy the key and update `.cursor/mcp.json`:

   Replace `YOUR_YOUTUBE_API_KEY_HERE` in the `youtube` server's `env.YOUTUBE_API_KEY` with your key.

6. Restart Cursor for changes to take effect.

## Location

- Server code: `tools/youtube-mcp/`
- Config: `.cursor/mcp.json` (gitignored; contains your API key)
