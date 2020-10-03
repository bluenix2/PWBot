import datetime
import sys
import traceback

import discord
from discord.ext import commands

import config
from cogs.utils import context, meta, settings

initial_extensions = (
    'cogs.admin',
    'cogs.threads',
    'cogs.lobby',
    'cogs.responses',
)


class PWBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='?', fetch_offline_members=False,
                         help_command=meta.PWBotHelp(command_attrs={
                            'brief': 'Displays all commands available',
                            'help': 'Displays all commands available,\
                                will display additional info if a command is specified'
                         })
                         )

        self.client_id = config.client_id
        self.uptime = None

        self.settings = settings.Settings()

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
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.author.send('This command cannot be used in private messages.')

        elif isinstance(error, commands.DisabledCommand):
            await ctx.author.send('Sorry, this command cannot be used at the moment.')

        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            if not isinstance(original, discord.HTTPException):
                print(f'Inside command {ctx.command.qualified_name}:', file=sys.stderr)
                traceback.print_tb(original.__traceback__)
                print(f'{original.__class__.__name__}: {original}', file=sys.stderr)

    async def process_commands(self, message):
        ctx = await self.get_context(message, cls=context.Context)

        try:
            await self.invoke(ctx)
        finally:
            # In case we have any outstanding database connections
            await ctx.release()

    def run(self):
        super().run(config.token, reconnect=True)