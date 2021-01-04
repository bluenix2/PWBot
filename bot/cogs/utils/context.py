import asyncio

import discord
from discord.ext import commands


class _ContextDBAcquire:
    """Helper class allowing the use of context managers,

    asyncpg already implements the context manager protocol,
    but this uses the cached db connection attribute
    """

    __slots__ = ('ctx', 'timeout')

    def __init__(self, ctx, timeout):
        self.ctx = ctx
        self.timeout = timeout

    def __await__(self):
        return self.ctx._acquire(self.timeout).__await__()

    async def __aenter__(self):
        await self.ctx._acquire(self.timeout)
        return self.ctx.db

    async def __aexit__(self, *args):
        await self.ctx.release()


class Context(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.pool = self.bot.pool
        self._db = None

    @property
    def db(self):
        """Cached database connection"""
        return self._db if self._db else self.pool

    async def _acquire(self, timeout):
        if self._db is None:
            self._db = await self.pool.acquire(timeout=timeout)
        return self._db

    async def acquire(self, timeout=300.0):
        """Acquires a database connection from the pool.
        Implements both ::

            async with ctx.acquire():
                await ctx.db.execute(...)

        and: ::

            await ctx.acquire()
            try:
                await ctx.db.execute(...)
            finally:
                await ctx.release()
        """
        return _ContextDBAcquire(self, timeout)

    async def release(self):
        """Releases the database connection"""
        if self._db is not None:
            await self.pool.release(self._db)
            self._db = None

    async def prompt(self, message, *, timeout=30.0, delete_after=True):
        """Prompt the context with an interactive confirmation dialog.

        Any acquired connection should be released before executing this.
        """
        msg = await self.send(message)

        confirmation = None

        def check(payload):
            # Kind of like global keyword. Allows us to get variables in parent functions
            nonlocal confirmation

            if payload.message_id != msg.id or payload.user_id != self.author.id:
                return False

            emoji = str(payload.emoji)

            if emoji == '\N{WHITE HEAVY CHECK MARK}':
                confirmation = True
                return True

            elif emoji == '\N{CROSS MARK}':
                # Flake8 is screaming that we don't use it, but
                # we do use it. So just to quiet it down.
                confirmation = False  # noqa: F841
                return True

            # It wasn't neither of the two emojis
            return False

        for reaction in ('\N{WHITE HEAVY CHECK MARK}', '\N{CROSS MARK}'):
            await msg.add_reaction(reaction)

        try:
            await self.bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
        except asyncio.TimeoutError:
            pass

        if delete_after:
            await msg.delete()

        return confirmation

    async def send_tag(self, name, conn=None):
        """Fetch a tag from the database, and send it
        in the current context.
        """
        conn = conn or self.db

        content = await self.bot.fetch_tag(name, conn=conn)
        if content:
            await self.send(content, allowed_mentions=discord.AllowedMentions.none())
        else:
            # Technically not a command, but easier than defining a new error
            raise commands.CommandNotFound('Tag not found.')
