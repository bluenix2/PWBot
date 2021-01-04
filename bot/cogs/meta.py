from datetime import datetime

import discord
from dateutil.relativedelta import relativedelta
from discord.ext import commands

from cogs.utils import Colour


class PWBotHelp(commands.HelpCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def generate_brief(self, help_doc):
        """Generate a brief from the help doc string."""
        # Quite useless function, but good if we want to change the functionality.
        return help_doc.split('.')[0]

    async def send_bot_help(self, mapping):
        bot = self.context.bot
        all_commands = await self.filter_commands(bot.commands, sort=True)

        embed = discord.Embed(
            title='All commands',
            colour=Colour.light_blue(),
        )
        for command in all_commands:
            embed.add_field(
                name=self.get_command_signature(command),
                value=command.brief or self.generate_brief(command.help),
                inline=False
            )

        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        if command.hidden:
            return

        await self.get_destination().send(embed=discord.Embed(
            title=command.name[0].upper() + command.name[1:],
            description='`{0}` {1}'.format(
                self.get_command_signature(command),
                command.help or command.brief,
            ),
            colour=Colour.light_blue(),
            )
        )

    async def send_group_help(self, group):
        if group.hidden:
            return

        all_commands = await self.filter_commands(group.commands, sort=True)

        embed = discord.Embed(
            title=group.name[0].upper() + group.name[1:],
            description='`{0}` {1}'.format(
                self.get_command_signature(group),
                group.help or group.brief,
            ),
            colour=Colour.light_blue(),
            )

        for command in all_commands:
            embed.add_field(
                name=self.get_command_signature(command),
                value=command.brief or self.generate_brief(command.help),
                inline=False
            )

        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error):
        return  # Do nothing


class Meta(commands.Cog):
    """Utilities for the bot itself."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def uptime(self, ctx):
        """Say how long the bot has been running."""
        delta = relativedelta(
            datetime.utcnow().replace(microsecond=0),
            self.bot.uptime.replace(microsecond=0),
        )
        await ctx.send(
            'I have been working for **{} weeks, {} days, {} hours, and {} minutes.**'.format(
                delta.weeks, (delta.days - delta.weeks * 7), delta.hours, delta.minutes
            )
        )

    @commands.command()
    @commands.is_owner()
    async def status(self, ctx, *, message=None):
        """Change the status of the bot, set a specific game activity."""
        game = discord.Game(message) if message else None
        await self.bot.change_presence(activity=game)
        await ctx.send('Changed status message.')


def setup(bot):
    bot.add_cog(Meta(bot))
