import click
from flask import current_app
from flask.cli import with_appcontext


@click.command("seed")
@click.option("--no-reset", is_flag=True, help="Do not delete the existing SQLite file first.")
@with_appcontext
def seed_command(no_reset: bool) -> None:
    from seed.seed import PASSWORD, run

    cfg = current_app.config["APP"]
    reset = not no_reset
    click.echo(f"Seeding {cfg.DATABASE_URL} (reset={reset})...")
    try:
        summary = run(cfg.DATABASE_URL, reset=reset)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Seeded {summary.properties} properties, {summary.users} users, {summary.guests} guests, "
               f"{summary.stays} stays, {summary.conversations} conversations, {summary.messages} messages, "
               f"{summary.work_orders} work orders.")
    click.echo(f"Log in as ava@hvh.test / {PASSWORD}")
