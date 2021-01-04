import asyncio
import datetime
import sys
import traceback

import asyncpg
import discord
from discord.ext import commands

import config
from cogs import meta, utils

initial_extensions = (
    'cogs.admin',
    'cogs.lobby',
    'cogs.logging',
    'cogs.meta',
    'cogs.misc',
    'cogs.roles',
    'cogs.suggestions',
    'cogs.tags',
    'cogs.tickets',
)


class PWBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents(guilds=True, messages=True, reactions=True,
                                  bans=True, members=True)
        allowed_mentions = discord.AllowedMentions(everyone=False, users=True, roles=False)
        super().__init__(command_prefix='?', fetch_offline_members=False,
                         help_command=meta.PWBotHelp(command_attrs={
                            'brief': 'Display all commands available',
                            'help': 'Display all commands available,\
                                will display additional info if a command is specified'
                         }), allowed_mentions=allowed_mentions, intents=intents
                         )

        self.client_id = config.client_id

        self.settings = utils.Settings()

        loop = asyncio.get_event_loop()
        try:
            self.pool = loop.run_until_complete(asyncpg.create_pool(config.postgresql))
        except Exception:
            print('Failed set up PostgreSQL pool, exiting')
            return

        for extension in initial_extensions:
            try:
                self.load_extension(extension)
            except commands.ExtensionError:
                print(f'Failed to load extension {extension}', file=sys.stderr)
                traceback.print_exc()

    async def on_ready(self):
        if not hasattr(self, 'uptime'):
            self.uptime = datetime.datetime.utcnow()

        print(f'Ready: {self.user} (ID: {self.user.id})')

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError):
            original = error.original
            if not isinstance(original, discord.HTTPException):
                print(f'Inside command {ctx.command.qualified_name}:', file=sys.stderr)
                traceback.print_tb(original.__traceback__)
                print(f'{original.__class__.__name__}: {original}', file=sys.stderr)

    async def invoke(self, ctx):
        # This is copied from commands.Bot.invoke, we still want to execute commands like usual
        if ctx.command is not None:
            self.dispatch('command', ctx)
            try:
                if await self.can_run(ctx, call_once=True):
                    await ctx.command.invoke(ctx)
                else:
                    raise commands.errors.CheckFailure(
                        'The global check once functions failed.'
                    )
            except commands.errors.CommandError as exc:
                await ctx.command.dispatch_error(ctx, exc)
            else:
                self.dispatch('command_completion', ctx)
        elif ctx.invoked_with:  # This is edited to first try to send a tag
            try:
                await ctx.send_tag(ctx.invoked_with)
            except commands.errors.CommandNotFound:
                exc = commands.errors.CommandNotFound(
                    'Command or tag "{}" is not found'.format(ctx.invoked_with)
                )
                self.dispatch('command_error', ctx, exc)

    async def process_commands(self, message):
        ctx = await self.get_context(message, cls=utils.Context)

        try:
            await self.invoke(ctx)
        finally:
            # In case we have any outstanding database connections
            await ctx.release()

    async def fetch_tag(self, name, *, conn=None):
        """Fetch a tag's content from the database."""
        conn = conn or self.pool

        query = """SELECT tag_content.value
                   FROM tags
                   INNER JOIN tag_content ON tag_content.id = tags.content_id
                   WHERE tags.name=$1 LIMIT 1;
                   """
        return await conn.fetchval(query, name)

    async def create_content(self, content, *, conn=None):
        """Create and insert content into the database, returns the created id
        so that it can be used to create a tag. This does not handle any errors
        that may occur while inserting.

        It is recommended that `conn` is through a transaction.
        """
        conn = conn or self.pool

        query = """INSERT INTO tag_content (value)
                   VALUES ($1)
                   RETURNING id;
                """
        return await conn.fetchval(query, content)

    async def create_tag(self, name, content_id, *, conn=None):
        """Create and insert a tag into the database, returns the created id.
        This doesn't handle any error that could happen while inserting.

        It is recommended that `conn` is through a transaction.
        """
        conn = conn or self.pool

        query = """INSERT INTO tags (content_id, name)
                   VALUES ($2, $1)
                   RETURNING id;
                """
        return await conn.execute(query, name, content_id)

    def run(self):
        super().run(config.token, reconnect=True)
