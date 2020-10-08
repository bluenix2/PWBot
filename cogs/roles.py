from discord.ext import commands


class Roles(commands.Cog):
    """Manages reaction roles."""
    def __init__(self, bot):
        self.bot = bot

        # A mapping of reaction ids to role ids.
        self.roles = self.bot.settings.roles

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.message_id != self.bot.settings.reaction_message:
            return

        role_id = self.roles[str(payload.emoji.id)]  # keys can't be ints
        if not role_id:
            return await self.bot.http.remove_reaction(
                payload.channel_id, payload.message_id,
                payload.emoji, payload.member.id,
            )

        await self.bot.http.add_role(payload.guild_id, payload.user_id, role_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.message_id != self.bot.settings.reaction_message:
            return

        role_id = self.roles[str(payload.emoji.id)]  # keys can't be ints
        if not role_id:
            return

        await self.bot.http.remove_role(payload.guild_id, payload.user_id, role_id)


def setup(bot):
    bot.add_cog(Roles(bot))