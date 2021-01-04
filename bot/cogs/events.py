from discord.ext import commands


class Events(commands.Cog):
    """Event specific code, for improving management of events."""
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.id != self.bot.settings.event_channel:
            return

        await message.add_reaction(f':survivor:{self.bot.settings.survivor_emoji}')


def setup(bot):
    bot.add_cog(Events(bot))
