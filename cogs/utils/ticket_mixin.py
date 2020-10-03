import enum
import io
import os
import zipfile

import discord
from discord.ext import commands


def ticket_only():
    async def predicate(ctx):
        if ctx.guild is None:
            return False

        query = 'SELECT EXISTS ( SELECT 1 FROM tickets WHERE channel_id=$1 LIMIT 1);'
        record = await ctx.db.fetchval(query, ctx.channel.id)

        return bool(record)
    return commands.check(predicate)


def author_only():
    async def predicate(ctx):
        if ctx.guild is None:
            return False

        query = 'SELECT author_id FROM tickets WHERE channel_id=$1;'
        author_id = await ctx.db.fetchval(query, ctx.channel.id)

        return author_id == ctx.author.id
    return commands.check(predicate)


class TicketType(enum.Enum):
    ticket = 0
    report = 1


class TicketMixin:
    """Central class for managing tickets.
    The following attributes must be defined when subclassing.
    You don't need to call init.

    Attributes
    -----------
    ticket_type: TicketType
        The type of ticket. This is used in queries.
    category_id: int
        The id of the category that the tickets will be created in
    open_message: str
        The content of the message the bot should send, will be formatted
        with a mention of the author.
    create_log: bool
        If logs should be created when closing the ticket.
    log_channel: Optional[int]
        The id of the channel that the log archives will be sent to.
    message_id: Optional[int]
        The id of the message that it should create tickets
        when reacted to.
        """

    def __init__(self):
        self._category = None

    @property
    def category(self):
        if not self._category:
            self._category = self.bot.get_channel(self.category_id)
        return self._category

    async def on_reaction(self, payload):
        if payload.message_id != self.message_id:
            return

        await self.bot.http.remove_reaction(
            payload.channel_id, payload.message_id,
            payload.emoji, payload.member.id,
        )

        if str(payload.emoji) != '\N{WHITE MEDIUM STAR}':  # Will be changed
            return

        await self._create_ticket(payload.member, None)

    async def on_open_command(self, ctx, issue):
        await ctx.message.delete()

        await self._create_ticket(ctx.author, issue, conn=ctx.db)

    async def _create_ticket(self, author, issue, *, conn=None):
        conn = conn or self.bot.pool  # We expect to be in a cog

        ticket_id = await conn.fetchval("SELECT nextval('ticket_id')")

        overwrites = {
            author: discord.PermissionOverwrite(
                read_messages=True,
            ),
        }
        overwrites.update(self.category.overwrites)

        channel = await self.category.create_text_channel(
            name='{0}-{1}'.format(ticket_id, issue or self.ticket_type.name),
            sync_permissions=True,
            overwrites=overwrites,
        )

        query = """INSERT INTO tickets (
                    id, channel_id, author_id, type, issue
                ) VALUES ($1, $2, $3, $4, $5);
        """
        await conn.execute(
            query, ticket_id, channel.id, author.id,
            self.ticket_type.value, issue[:90] if issue else None
        )

        await channel.send(author.mention, embed=discord.Embed(
            description=self.open_message.format(author.mention),
            colour=discord.Colour.greyple(),
        ))

        return channel

    async def on_close_command(self, ctx, reason):
        query = 'SELECT * from tickets WHERE channel_id=$1;'
        record = await ctx.db.fetchrow(query, ctx.channel.id)

        if not record:
            return

        if self.create_log:
            log = await self._generate_log(ctx.channel, record)

            issue = '-' + record['issue'] if record['issue'] else ''
            filename = f"transcript-{record['id']}{issue}.zip"
            transcript = discord.File(
                log,
                filename=filename
            )

            channel = self.bot.get_channel(self.log_channel)
            # We send the file name so that it's easily searched in discord
            await channel.send(filename, file=transcript)

        await ctx.channel.delete(reason=reason)

    async def _generate_log(self, channel, record):
        """Create a log archive with transcript and attachments."""
        messages = [f"""Transcript of ticket {record['id']} "{record['issue']}":\n"""]

        attachments = []
        async for message in channel.history(oldest_first=True):
            messages.append(
                "[{2}] {0.author} ({0.author.id}){1}: {0.content}".format(
                    message, ' (attachment)' if message.attachments else '',
                    message.created_at.strftime('%Y %b %d %H:%M:%S')
                )
            )
            attachments.extend(message.attachments)

        memory = io.BytesIO()
        archive = zipfile.ZipFile(memory, 'a', zipfile.ZIP_DEFLATED, False)

        for index in range(len(attachments)):

            archive.writestr(
                'attachment-' + str(index) + os.path.splitext(attachments[index].filename)[1],
                await attachments[index].read()
            )

        archive.writestr('transcript.txt', '\n'.join(messages))
        archive.close()

        memory.seek(0)
        return memory