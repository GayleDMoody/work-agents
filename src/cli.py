"""CLI entry point for the Work Agents system."""

import asyncio
import click
import uvicorn

from src.observability.logging import setup_logging, get_logger


@click.group()
@click.option("--log-level", default="INFO", help="Log level")
@click.option("--json-logs", is_flag=True, help="Output logs as JSON")
def cli(log_level: str, json_logs: bool):
    """Work Agents - Multi-agent software team orchestration."""
    setup_logging(log_level=log_level, json_output=json_logs)


@cli.command()
@click.option("--host", default="0.0.0.0", help="API server host")
@click.option("--port", default=8000, type=int, help="API server port")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool):
    """Start the API server."""
    log = get_logger("cli")
    log.info("starting_server", host=host, port=port)
    uvicorn.run(
        "src.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@cli.command()
@click.argument("ticket_key")
@click.option("--summary", default="", help="Ticket summary")
@click.option("--description", default="", help="Ticket description")
@click.option("--crew-type", default="full", help="Crew type: full, backend_bug")
def run(ticket_key: str, summary: str, description: str, crew_type: str):
    """Process a single Jira ticket through the crew pipeline."""
    log = get_logger("cli")
    log.info("processing_ticket", ticket_key=ticket_key, crew_type=crew_type)

    async def _run():
        from src.factory import create_crew

        crew = create_crew(ticket_type=crew_type)
        result = await crew.kickoff(inputs={
            "ticket_key": ticket_key,
            "ticket_summary": summary or f"Ticket {ticket_key}",
            "ticket_description": description or "No description provided",
        })

        log.info(
            "crew_finished",
            ticket_key=ticket_key,
            success=result.success,
            duration=f"{result.duration_seconds:.1f}s",
            tasks_completed=len(result.tasks_output),
            total_tokens=result.token_usage.total_input_tokens + result.token_usage.total_output_tokens,
            cost=f"${result.token_usage.total_cost_usd:.4f}",
        )

        if result.tasks_output:
            log.info("task_outputs:")
            for to in result.tasks_output:
                log.info(f"  [{to.agent}] {to.description[:60]}... -> {to.raw[:100]}...")

        return result

    result = asyncio.run(_run())
    if not result.success:
        raise SystemExit(1)


@cli.command()
@click.option("--jql", required=True, help="JQL query for tickets to process")
@click.option("--interval", default=60, type=int, help="Poll interval in seconds")
def watch(jql: str, interval: int):
    """Watch for new Jira tickets and process them."""
    log = get_logger("cli")
    log.info("starting_watcher", jql=jql, interval=interval)

    async def _watch():
        from src.factory import create_crew
        from src.settings import get_settings

        settings = get_settings()
        if not settings.jira.server_url or not settings.jira.api_token:
            log.error("jira_not_configured", message="Set WORK_AGENTS_JIRA_* env vars")
            return

        from src.integrations.jira_client import JiraClient

        jira = JiraClient(
            server_url=settings.jira.server_url,
            email=settings.jira.email,
            api_token=settings.jira.api_token,
        )

        log.info("watcher_ready", jql=jql, poll_interval=interval)

        processed: set[str] = set()
        while True:
            try:
                tickets = await jira.search_tickets(jql)
                for ticket in tickets:
                    key = ticket["key"]
                    if key not in processed:
                        processed.add(key)
                        log.info("processing_new_ticket", ticket_key=key)
                        crew = create_crew()
                        result = await crew.kickoff(inputs={
                            "ticket_key": key,
                            "ticket_summary": ticket.get("summary", ""),
                            "ticket_description": "",
                        })
                        log.info("ticket_done", ticket_key=key, success=result.success)
            except Exception as e:
                log.error("watch_cycle_error", error=str(e))

            await asyncio.sleep(interval)

    asyncio.run(_watch())


def main():
    cli()


if __name__ == "__main__":
    main()
