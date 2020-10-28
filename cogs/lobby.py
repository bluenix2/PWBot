import asyncio

import discord
from discord.ext import commands

from cogs.utils import colours

# INSTRUCTIONS
# Disclaimer: If possible try to commit these in several commits.
# At least one per feature. It aids me a lot in squashing. As these two
# features should be in two seperate commits.
# I rather have 100 commits, one per letter change, than 1 commit that I need to
# seperate in some way. Not a big deal if you accidentally do it. But try if possible.

# First we want to be able to name lobbies. So you can effectively do
# ?lobby 5 group alpha
# And it will in some way in the lobby embed let you know
# that this is the "group alpha" lobby.

# Secondly, a new feature would be. That you can disband lobbies
# with a reason. So it'll say in some nice way that maybe it took to long
# or you all agreed that it was a bad idea.
# This means that it can also specifically say that the lobby timed out.


def lobby_channel_only():
    async def predicate(ctx):
        return ctx.channel.id in (
            ctx.bot.settings.beta_channel,
            ctx.bot.settings.tournaments_channel
        )
    return commands.check(predicate)


class Lobby:
    """Represents a waiting beta lobby."""

    # Since we're now passing name we need to update the parameters
    def __init__(self, manager, owner_id, message, required_players):
        # Also define name as an attribute
        self.manager = manager
        self.owner_id = owner_id
        self.required_players = required_players

        self.message = message
        self.players = {owner_id}

        async def timeout(timeout=21600):
            await asyncio.sleep(timeout)

            # We should pass that the lobby timed out
            # So pass that as a reason
            await self.disband(timeout=True)

        self.timeout = asyncio.create_task(timeout())

    # We need to update parameters to accept the reason
    async def disband(self, *, timeout=False):
        if not timeout:
            self.timeout.cancel()

        # However you integrate it is up to you
        # but remember that it should be able to handle
        # that the reason is None
        self.manager.lobbies.remove(self)
        await self.message.clear_reactions()
        await self.message.channel.send(
            '<@{0}> your lobby was disbanded.'.format(
                self.owner_id
            )
        )

        description = 'This lobby was disbanded.'
        await self.message.edit(embed=discord.Embed(
            title='Lobby Disbanded!',
            description=description,
            colour=colours.unvaulted_red(),
        ))


class LobbyManager(commands.Cog):
    """Cog for managing waiting beta lobbies."""

    def __init__(self, bot):
        self.bot = bot

        self.lobbies = set()

    def get_lobby_by_owner(self, owner_id):
        for lobby in self.lobbies:
            if lobby.owner_id == owner_id:
                return lobby

    def get_lobby_by_message(self, message_id):
        for lobby in self.lobbies:
            if lobby.message.id == message_id:
                return lobby

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.channel_id not in (
                self.bot.settings.beta_channel,
                self.bot.settings.tournaments_channel):
            return

        if payload.user_id == self.bot.client_id:     # ignore the bot's reacts
            return

        if payload.emoji.id != self.bot.settings.high5_emoji:
            return

        lobby = self.get_lobby_by_message(payload.message_id)

        if lobby is None:
            return

        if payload.user_id == lobby.owner_id and lobby.owner_id in lobby.players:
            return await self.bot.http.remove_own_reaction(
                payload.channel_id, payload.message_id,
                ':high5:{}'.format(self.bot.settings.high5_emoji),
            )

        lobby.players.add(payload.user_id)

        if len(lobby.players) == 1:
            await self.bot.http.remove_own_reaction(
                payload.channel_id, payload.message_id,
                ':high5:{}'.format(self.bot.settings.high5_emoji),
            )

        elif lobby.required_players == len(lobby.players):
            await lobby.message.clear_reactions()
            await lobby.message.channel.send(
                'You have enough players to start a game! ' + ', '.join(
                    '<@{0}>'.format(player) for player in lobby.players
                ),
            )
            self.lobbies.remove(lobby)

            description = 'This lobby reached the desired amount of players.'
            await lobby.message.edit(embed=discord.Embed(
                title='Lobby Full!',
                description=description,
                colour=colours.apricot(),
            ))

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.channel_id not in (
                self.bot.settings.beta_channel,
                self.bot.settings.tournaments_channel):
            return

        if payload.user_id == self.bot.client_id:
            return

        if payload.emoji.id != self.bot.settings.high5_emoji:
            return

        lobby = self.get_lobby_by_message(payload.message_id)

        if lobby is None:
            return

        lobby.players.remove(payload.user_id)

        if len(lobby.players) == 0:
            await self.bot.http.add_reaction(
                payload.channel_id, payload.message_id,
                ':high5:{}'.format(self.bot.settings.high5_emoji),
            )

    @commands.group(invoke_without_command=True)
    @lobby_channel_only()
    async def lobby(self, ctx, players: int = 5, *, name=None):
        """
        Open a managed waiting lobby to gather players. This then pings all players when full.
        """
        # We want to be able to name lobbies. For example with tournaments
        # when there are several groups going at the same time.
        # This can also be used to explain some custom settings.

        # How you integrate this is up to you, maybe in the embed title or elsewhere.
        lobby = self.get_lobby_by_owner(ctx.author.id)

        if lobby:
            return await ctx.send('Please disband your old lobby before opening a new one.')

        if players < 2 or players > 8:
            return

        message = await ctx.send(embed=discord.Embed(
            title='Looking for players!',
            description='If you are available for a game, react below.',
            colour=colours.cyan(),
        ))

        # We should pass name into this.
        self.lobbies.add(Lobby(self, ctx.author.id, message, players))

        await message.add_reaction(':high5:{}'.format(self.bot.settings.high5_emoji))

    @lobby.command(name='disband')
    @lobby_channel_only()
    async def lobby_disband(self, ctx, *, reason=None):
        """Disband an old lobby."""
        # You should be able to have a closing reason.
        lobby = self.get_lobby_by_owner(ctx.author.id)
        if lobby is None:
            return

        # We should pass this reason to disband()
        await lobby.disband()


def setup(bot):
    bot.add_cog(LobbyManager(bot))
