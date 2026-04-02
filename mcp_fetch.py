import asyncio
from dotenv import load_dotenv
from agents import Agent, Runner, trace
from agents.mcp import MCPServerStdio
import os

load_dotenv(override=True)


async def main():
    # Start MCP fetch server
    fetch_params = {"command": "uvx", "args": ["mcp-server-fetch"]}

    async with MCPServerStdio(
        params=fetch_params,
        client_session_timeout_seconds=60
    ) as server:

        # Get available tools
        fetch_tools = await server.list_tools()

        print("Available MCP Tools:", fetch_tools)

        # Create agent with MCP tools
        agent = Agent(
            name="Web Scraper Agent",
            instructions=(
                "You are a web scraping assistant. "
                "Use the fetch tool to extract content from websites and summarize it clearly."
            ),
            tools=fetch_tools
        )

        # Run task
        result = await Runner.run(
            agent,
            input="Fetch and summarize the content of https://example.com"
        )

        print("\nFinal Output:\n", result.final_output)


if __name__ == "__main__":
    asyncio.run(main())