import asyncio
import datetime
import time

import discord
from discord.ext import commands

from cogs.utils import Colour


class ModLogging(commands.Cog):
    """Logging listeners for moderation actions."""
    def __init__(self, bot):
        self.bot = bot
        self._automod_channel = None

    @property
    def automod_channel(self):
        if not self._automod_channel:
            self._automod_channel = self.bot.get_channel(self.bot.settings.automod_channel)
        return self._automod_channel

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        timestamp = datetime.datetime.utcnow()

        if member.joined_at is None:
            return

        await asyncio.sleep(1)

        log = None
        limit_timestamp = datetime.datetime.utcfromtimestamp(time.time() - 60)

        # This has a little bit higher treshold because there is no guarantee to find the log.
        guild = member.guild
        async for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=25):
            if member.joined_at > entry.created_at or entry.created_at < limit_timestamp:
                # We've missed it, or it's not there
                break

            if entry.target == member:
                log = entry
                break

        if not log:
            return

        embed = discord.Embed(
            title='Member Kicked',
            description=f'{member} (ID: {member.id})',
            colour=Colour.apricot(),
            timestamp=timestamp,
        )
        embed.set_thumbnail(url=member.avatar_url)

        embed.set_author(
            name=f'{log.user.display_name} (ID: {log.user.id})',
            icon_url=log.user.avatar_url
        )

        if log.reason:
            embed.add_field(name='Reason', value=log.reason)

        await self.automod_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):  # noqa: C901
        timestamp = datetime.datetime.utcnow()

        # Filter out all other changes than role updates
        if before.status != after.status:
            return
        elif before.activities != after.activities:
            return
        elif before.nick != after.nick:
            return

        role = self.bot.settings.timed_out_role

        # We're touching some internal lib implementation for performance.
        # This will match if both has it, or doesn't. As in, some other role changed.
        if before._roles.has(role) == after._roles.has(role) and before is not after:
            return

        await asyncio.sleep(1)

        log = None
        limit_timestamp = datetime.datetime.utcfromtimestamp(time.time() - 60)

        entries = after.guild.audit_logs(
            action=discord.AuditLogAction.member_role_update, limit=25
        )
        async for entry in entries:
            if entry.target == after and entry.created_at > limit_timestamp:
                log = entry
                break

        if not log and before is after:
            # There will be no way to figure out if it was added or removed
            return

        def has_role(roles):
            for item in roles:
                if item.id == role:
                    return True
            return False

        title = None
        colour = None

        before_has = has_role(log.before.roles) if log else before._roles.has(role)
        after_has = has_role(log.after.roles) if log else after._roles.has(role)

        if not before_has and after_has:
            title = 'Member Timed Out'
            colour = Colour.apricot()
        elif before_has and not after_has:
            title = 'Member Un-timed Out'
            colour = Colour.light_blue()

        if title is None or colour is None:
            return

        embed = discord.Embed(
            title=title,
            description=f'{after} (ID: {after.id})',
            colour=colour,
            timestamp=timestamp,
        )
        embed.set_thumbnail(url=after.avatar_url)

        if log:
            embed.set_author(
                name=f'{log.user.display_name} (ID: {log.user.id})',
                icon_url=log.user.avatar_url
            )

            if log.reason:
                embed.add_field(name='Reason', value=log.reason)

        await self.automod_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        timestamp = datetime.datetime.utcnow()

        await asyncio.sleep(1)

        log = None
        limit_timestamp = datetime.datetime.utcfromtimestamp(time.time() - 60)

        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=10):
            if entry.target == user and entry.created_at > limit_timestamp:
                log = entry
                break

        embed = discord.Embed(
            title='Member Banned',
            description=f'{user} (ID: {user.id})',
            colour=Colour.unvaulted_red(),
            timestamp=timestamp,
        )
        embed.set_thumbnail(url=user.avatar_url)

        if log:
            embed.set_author(
                name=f'{log.user.display_name} (ID: {log.user.id})',
                icon_url=log.user.avatar_url
            )

            if log.reason:
                embed.add_field(name='Reason', value=log.reason)

        await self.automod_channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        timestamp = datetime.datetime.utcnow()

        await asyncio.sleep(1)

        log = None
        limit_timestamp = datetime.datetime.utcfromtimestamp(time.time() - 60)

        async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=10):
            if entry.target == user and entry.created_at > limit_timestamp:
                log = entry
                break

        embed = discord.Embed(
            title='Member Unbanned',
            description=f'{user} (ID: {user.id})',
            colour=Colour.light_blue(),
            timestamp=timestamp,
        )
        embed.set_thumbnail(url=user.avatar_url)

        if log:
            embed.set_author(
                name=f'{log.user.display_name} (ID: {log.user.id})',
                icon_url=log.user.avatar_url
            )

            if log.reason:
                embed.add_field(name='Reason', value=log.reason)

        await self.automod_channel.send(embed=embed)


def setup(bot):
    bot.add_cog(ModLogging(bot))
