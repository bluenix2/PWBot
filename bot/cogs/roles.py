import enum

import discord
from discord.ext import commands

from cogs.utils import Colour


class RoleType(enum.Enum):
    ping = 0
    language = 1


class Roles(commands.Cog):
    """Manages reaction roles for both language and ping roles."""
    def __init__(self, bot):
        self.bot = bot

        self._role_channel = None

    @property
    def messages(self):
        # Defining it directly means it doesn't get changed
        # when the setting gets set, this is a work-around
        return {
            self.bot.settings.pings_message: RoleType.ping,
            self.bot.settings.language_message: RoleType.language,
        }

    @property
    def role_channel(self):
        if not self._role_channel:
            self._role_channel = self.bot.get_channel(self.bot.settings.role_channel)
        return self._role_channel

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        role_type = self.messages.get(payload.message_id)
        # The message is not pings_message or language_message
        if not role_type:
            return

        if payload.user_id == self.bot.client_id:
            return

        query = 'SELECT role_id FROM roles WHERE reaction=$1 AND type=$2;'
        role_id = await self.bot.pool.fetchval(query, str(payload.emoji), role_type.value)
        if not role_id:
            # Someone reacted with an emoji that wasn't set up for *this message*.
            # We remove it as to clarify what emojis actually work.
            return await self.bot.http.remove_reaction(
                payload.channel_id, payload.message_id,
                payload.emoji._as_reaction(), payload.user_id
            )

        await self.bot.http.add_role(payload.guild_id, payload.user_id, role_id)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        role_type = self.messages.get(payload.message_id)
        # The message is not pings_message or language_message
        if not role_type:
            return

        query = 'SELECT role_id FROM roles WHERE reaction=$1 AND type=$2;'
        role_id = await self.bot.pool.fetchval(query, str(payload.emoji), role_type.value)
        if not role_id:
            # At this point it was the bot that removed the reaction ( see above ),
            # so we just ignore because there is no role to remove.
            return

        await self.bot.http.remove_role(payload.guild_id, payload.user_id, role_id)

    async def _add_role(self, emoji, role, role_type, name, field, message_id, *, conn=None):
        if not conn:
            conn = self.bot.pool

        query = """INSERT INTO roles (
                    reaction, name, role_id, type, description
                ) VALUES ($1, $2, $3, $4, $5) RETURNING *;
        """
        record = await conn.fetchrow(query, emoji, name, role.id, role_type.value, field)

        message = await self.role_channel.fetch_message(message_id)

        message.embeds[0].add_field(
            name=record['name'],
            value=record['description'],
            inline=True
        )
        await message.edit(embed=message.embeds[0])

        await message.add_reaction(record['reaction'].strip('<>'))

    async def _remove_role(self, emoji, message_id, role_type, *, conn=None):
        if not conn:
            conn = self.bot.pool

        query = 'DELETE FROM roles WHERE reaction=$1 AND type=$2 RETURNING *;'
        record = await conn.fetchrow(query, emoji, role_type.value)
        message = await self.role_channel.fetch_message(message_id)

        index = [em.name for em in message.embeds[0].fields].index(record['name'])
        message.embeds[0].remove_field(index)

        await message.edit(embed=message.embeds[0])

        await message.clear_reaction(emoji.strip('<>'))

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def language(self, ctx):
        """Manage language roles."""
        # This is only meant as a container for the language roles management
        await ctx.send_help('language')  # We send help for this group

    @language.command(name='add')
    # We already check for owner in our parent
    async def language_add(self, ctx, emoji, role: discord.Role, name, *, field):
        """Add a new language role to the reaction embed."""
        await self._add_role(
            emoji, role, RoleType.language, name,
            field, self.bot.settings.language_message,
            conn=ctx.db
        )

    @language.command(name='remove')
    # We already check for owner in our parent
    async def language_remove(self, ctx, emoji):
        """Remove a language from the reaction embed."""
        await self._remove_role(
            emoji, self.bot.settings.language_message, RoleType.language,
            conn=ctx.db
        )

    @language.command(name='send')
    # We already check for owner in our parent
    async def language_send(self, ctx):
        """Send the initial reaction embed for language roles."""
        prompt = 'Are you sure you would like to send the language reaction message?'
        if not await ctx.prompt(prompt):
            return

        await ctx.message.delete()

        description = '\n'.join((
            'To help find games in your langauges we have created ' +
            'some roles for *you* to ping instead.',
            'This does mean that these roles will be pinged a lot, so only assign ' +
            'them to yourself if you are fine with '
            'getting pinged a lot by members in <#540999156660174878>.\n',

            'React to this message to assign yourself the appropriate role.',
            'If you have any questions please ping a Community Manager',
        ))

        embed = discord.Embed(
            title='Language Roles',
            description=description,
            colour=Colour.light_blue()
        )

        records = await ctx.db.fetch(
            'SELECT * FROM roles WHERE type=$1;', RoleType.language.value
        )

        for record in records:
            embed.add_field(
                name=record['name'],
                value=record['description'],
                inline=True
            )

        message = await ctx.send(embed=embed)
        self.bot.settings.language_message = message.id

        for record in records:
            await message.add_reaction(record['reaction'].strip('<>'))

    @commands.group(invoke_without_command=True)
    @commands.is_owner()
    async def pings(self, ctx):
        """Manage ping roles."""
        # This is only meant as a container for the ping roles management
        await ctx.send_help('pings')  # We send help for this group

    @pings.command(name='add')
    # We already check for owner in the parent command
    async def pings_add(self, ctx, emoji, role: discord.Role, name, *, field):
        """Add a new ping role to the reaction embed."""
        await self._add_role(
            emoji, role, RoleType.ping, name,
            field, self.bot.settings.pings_message,
            conn=ctx.db
        )

    @pings.command(name='remove')
    # We already do a check for bot owner
    async def pings_remove(self, ctx, emoji):
        """Remove a language role from the embed message."""
        await self._remove_role(
            emoji, self.bot.settings.pings_message, RoleType.ping,
            conn=ctx.db
        )

    @pings.command(name='send')
    # Already checking for bot owner
    async def pings_send(self, ctx):
        """Send the initial reaction embed for ping roles."""
        prompt = 'Are you sure you would like to send the pings reaction message?'
        if not await ctx.prompt(prompt):
            return

        await ctx.message.delete()

        description = '\n'.join((
            "To avoid pinging everyone we've created a few roles to ping instead.\n",

            'React to this message to assign the appropriate role.',
            'If you have any questions feel free to ping a Community Manager.',
        ))
        embed = discord.Embed(
            title='Role Management',
            description=description,
            colour=Colour.light_blue()
        )

        records = await ctx.db.fetch(
            'SELECT * FROM roles WHERE type=$1;', RoleType.ping.value
        )

        if not records:
            return

        for record in records:
            embed.add_field(
                name=record['name'],
                value=record['description'],
                inline=False
            )

        message = await ctx.send(embed=embed)
        self.bot.settings.pings_message = message.id

        for record in records:
            await message.add_reaction(record['reaction'].strip('<>'))


def setup(bot):
    bot.add_cog(Roles(bot))
