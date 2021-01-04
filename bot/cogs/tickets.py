import enum
import io
import os
import zipfile

import discord
from discord.ext import commands

from cogs.utils import Colour, is_mod


def ticket_only():
    """Check for channel being a ticket,
    can only be used on commands inside TicketMixin subclasses
    because it uses the ticket_type attribute.
    """
    async def predicate(ctx):
        if ctx.guild is None:
            return False

        query = """SELECT EXISTS (
                SELECT 1 FROM tickets WHERE channel_id=$1 AND type=$2 LIMIT 1
            );
        """
        record = await ctx.db.fetchval(query, ctx.channel.id, ctx.cog.ticket_type.value)

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


class TicketState(enum.Enum):
    open = 0
    closed = 1


class _BaseManager(commands.Cog):
    """Central class for managing tickets.
    The following attributes must be defined when subclassing.

    Attributes
    -----------
    ticket_type: TicketType
        The type of ticket. This is used in queries.
    category_id: int
        The id of the category that the tickets will be created in
    open_message: str
        The content of the message embed the bot should send.
    status_channel_id: int
        The id of the channel where updates and statuses on tickets are kept.
    create_log: bool
        If logs should be created when closing the ticket.
    log_channel_id: Optional[int]
        The id of the channel that the log archives will be sent to.
    message_id: Optional[int]
        The id of the message that it should create tickets
        when reacted to.
        """

    def __init__(self, bot):
        self.bot = bot
        self._category = None
        self._status_channel = None
        self._log_channel = None

    @property
    def category(self):
        if not self._category:
            self._category = self.bot.get_channel(self.category_id)
        return self._category

    @property
    def status_channel(self):
        if not self._status_channel:
            self._status_channel = self.bot.get_channel(self.status_channel_id)
        return self._status_channel

    @property
    def log_channel(self):
        if not self._log_channel:
            self._log_channel = self.bot.get_channel(self.log_channel_id)
        return self._log_channel

    async def get_open_by_author(self, author_id):
        query = 'SELECT channel_id FROM tickets WHERE author_id=$1 AND state=$2 AND type=$3;'
        channel_id = await self.bot.pool.fetchval(
            query, author_id, TicketState.open.value, self.ticket_type.value
        )

        return channel_id

    async def on_reaction(self, payload):
        if payload.message_id != self.message_id:
            return

        if payload.user_id == self.bot.client_id:
            return

        await self.bot.http.remove_reaction(
            payload.channel_id, payload.message_id,
            payload.emoji._as_reaction(), payload.member.id,
        )

        if payload.emoji.id != self.bot.settings.high5_emoji:
            return

        open_channel = await self.get_open_by_author(payload.user_id)
        if open_channel:
            return await self.bot.http.send_message(
                open_channel, '<@{0}> you already have an open {1} in here.'.format(
                    payload.user_id, self.ticket_type.name
                ))

        await self._create_ticket(payload.member, None)

    async def on_open_command(self, ctx, issue, *, user=None):
        author = user or ctx.author

        await ctx.message.delete()

        open_channel = await self.get_open_by_author(author.id)
        if open_channel:
            return await ctx.send('{0} already has an open {1}: <#{2}>'.format(
                    author.mention, self.ticket_type.name, open_channel
                ), delete_after=10
            )

        channel, record = await self._create_ticket(author, issue, conn=ctx.db)

        # Only for tickets, reports should stay anonymous
        if self.ticket_type == TicketType.ticket:
            await ctx.send('Opened ticket #{} in {} for {}.'.format(
                record['id'], channel.mention, author.mention
            ), allowed_mentions=discord.AllowedMentions(users=False))
        else:
            await ctx.send('Opened {} #{} in {}.'.format(
                self.ticket_type.name, record['id'], channel.mention
            ))

    async def _create_ticket(self, author, issue, *, conn=None):
        conn = conn or self.bot.pool  # We expect to be in a cog

        ticket_id = await conn.fetchval("SELECT nextval('ticket_id');")

        overwrites = {
            author: discord.PermissionOverwrite(
                read_messages=True
            )
        }
        overwrites.update(self.category.overwrites)

        channel = await self.category.create_text_channel(
            name='{0}-{1}'.format(ticket_id, issue[:90] if issue else author.display_name),
            sync_permissions=True, overwrites=overwrites,
            reason='Creating ticket #{0}: {1}'.format(ticket_id, issue)
        )

        query = """INSERT INTO tickets (
                    id, channel_id, author_id, type, issue
                ) VALUES ($1, $2, $3, $4, $5) RETURNING *;
        """
        record = await conn.fetchrow(
            query, ticket_id, channel.id, author.id,
            self.ticket_type.value, issue[:90] if issue else None
        )

        await channel.send(
            'Welcome {0}'.format(author.mention),
            embed=discord.Embed(
                description=self.open_message,
                colour=Colour.light_blue(),
            )
        )

        title = '{} #{}{}'.format(
            self.ticket_type.name[0].upper() + self.ticket_type.name[1:],
            record['id'], ' - {}'.format(issue[:235]) if issue else ''
        )

        embed = discord.Embed(
            title=title,
            colour=Colour.cyan()
        )

        embed.set_author(name=author, icon_url=author.avatar_url)

        message = await self.status_channel.send(embed=embed)

        await conn.execute(
            'UPDATE tickets SET status_message_id=$1 WHERE id=$2',
            message.id, record['id']
        )

        return channel, record

    async def _generate_log(self, channel, record):
        """Create a log archive with transcript and attachments."""
        messages = ["""Transcript of ticket {0} "{1}" opened by user {2}:\n""".format(
            record['id'], record['issue'], record['author_id']
        )]

        attachments = []
        async for message in channel.history(oldest_first=True):
            messages.append(
                "[{0}] {1.author} ({1.author.id}){2}: {1.content}".format(
                    message.created_at.strftime('%Y %b %d %H:%M:%S'),
                    message, ' (attachment)' if message.attachments else '',
                )
            )
            attachments.extend(message.attachments)

        memory = io.BytesIO()
        archive = zipfile.ZipFile(memory, 'a', zipfile.ZIP_DEFLATED, False)

        archive.writestr('transcript.txt', '\n'.join(messages))

        for index in range(len(attachments)):

            archive.writestr(
                'attachment-' + str(index) + os.path.splitext(attachments[index].filename)[1],
                await attachments[index].read()
            )
        archive.close()

        memory.seek(0)
        return memory

    async def on_close_command(self, ctx, reason):
        query = 'SELECT * from tickets WHERE channel_id=$1;'
        record = await ctx.db.fetchrow(query, ctx.channel.id)

        if not record:
            return

        query = 'UPDATE tickets SET state=$1 WHERE channel_id=$2'
        await ctx.db.execute(query, TicketState.closed.value, record['channel_id'])

        log_message = None
        if self.create_log:
            await ctx.send('Locked the channel. Creating logs, this may take a while.')

            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(
                    read_messages=False
                ),
                self.bot.user: discord.PermissionOverwrite(
                    read_messages=True
                )
            }
            await ctx.channel.edit(
                overwrites=overwrites,
                reason='Locking ticket while creating logs as to not disrupt.'
            )

            archive = await self._generate_log(ctx.channel, record)

            issue = '-' + record['issue'] if record['issue'] else ''
            filename = f"log-{record['id']}{issue}.zip"
            log = discord.File(archive, filename=filename)

            # We send the file name so that it's easily searched in discord
            log_message = await self.log_channel.send(filename, file=log)

        message = await self.status_channel.fetch_message(record['status_message_id'])
        embed = message.embeds[0]

        embed.description = reason
        embed.colour = Colour.apricot()

        if log_message:
            embed.add_field(name='Log', value=f'[Jump!]({log_message.jump_url})')

        embed.set_footer(
            text=f'{ctx.author} ({ctx.author.id})',
            icon_url=ctx.author.avatar_url
        )

        await message.edit(embed=embed)

        await ctx.channel.delete(
            reason='Closing ticket #{0} because: {1}'.format(record['id'], reason)
        )


class TicketManager(_BaseManager):
    """Cog managing all normal tickets for help."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ticket_type = TicketType.ticket
        self.category_id = self.bot.settings.ticket_category

        self.open_message = '\n'.join((
            'Thank you for opening a ticket, what can we help you with?',
            'Please explain what you need help with and we will get back with you.\n',

            'If you are having technical issues, please post a log. See `?log`.',
            'Otherwise, if your issue is related to in-game bans or crate purchasing please ' +
            'post a link to your steam profile.'
        ))

        self.status_channel_id = self.bot.settings.ticket_status_channel

        self.create_log = True
        self.log_channel_id = self.bot.settings.log_channel

    @property
    def message_id(self):
        # Defining the attribute directly means it doesn't get changed
        # when bot.settings.ticket_message gets set, this is a work-around
        return self.bot.settings.ticket_message

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.on_reaction(payload)

    @commands.group(invoke_without_command=True)
    async def ticket(self, ctx, *, issue=None):
        """Open a ticket or send a help message. Parent command for ticket management."""
        if issue:  # Aid users in opening tickets
            return await ctx.invoke(self.ticket_open, issue=issue)

        await ctx.send_tag('ticket')

    @ticket.command(name='open')
    async def ticket_open(self, ctx, *, issue=None):
        """Open a help ticket."""
        await self.on_open_command(ctx, issue)

    @ticket.command(name='openas')
    @is_mod()
    async def ticket_openas(self, ctx, user: discord.Member, *, issue=None):
        """Open a ticket for a member. This can only be used by mods."""
        await self.on_open_command(ctx, issue, user=user)

    @ticket.command(name='adduser')
    @ticket_only()
    @commands.check_any(author_only(), is_mod())
    async def ticket_adduser(self, ctx, user: discord.User):
        """Add a member to the help ticket."""
        await ctx.channel.set_permissions(user, read_messages=True)

        await ctx.send(
            "Welcome {0}, you were added to this ticket.".format(user.mention)
        )

    @ticket.command(name='close')
    @ticket_only()
    @is_mod()
    async def ticket_close(self, ctx, *, reason=None):
        """Close the ticket and create an archive. The reason should be a summary."""
        await self.on_close_command(ctx, reason)

    @ticket.command(name='megamode')
    @commands.is_owner()
    async def ticket_megamode(self, ctx):
        """Limit the help channel and force everyone to react and open tickets."""
        await ctx.message.delete()
        help_channel = ctx.guild.get_channel(self.bot.settings.help_channel)

        if self.bot.settings.ticket_message == 0:
            await help_channel.set_permissions(ctx.guild.default_role, send_messages=False)

            description = '\n'.join((
                'We have temporarily limited the help channels at the moment. To get help '
                'please open a ticket where you will get access to a private channel.',
                '**To get help simply react below with <:high5:{}>!**'.format(
                    self.bot.settings.high5_emoji
                )
            ))

            message = await help_channel.send(embed=discord.Embed(
                title='Help',
                description=description,
                colour=Colour.light_blue()
            ))
            self.bot.settings.ticket_message = message.id

            await message.add_reaction(':high5:{}'.format(self.bot.settings.high5_emoji))

        else:
            await help_channel.set_permissions(ctx.guild.default_role, send_messages=None)

            await self.bot.http.delete_message(
                help_channel.id,
                self.bot.settings.ticket_message
            )

            self.bot.settings.ticket_message = 0


class ReportManager(_BaseManager):
    """Cog managing all report tickets for reporting players."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.ticket_type = TicketType.report
        self.category_id = self.bot.settings.report_category

        self.open_message = '\n'.join((
            'Thank you for reporting, please provide all the evidence.',
            'Feel free to use the following template: ```',
            'Username/Steam ID:',
            'Reason:',
            'Description of incident:',
            'Evidence (Video or screenshots):',
            '```',
        ))

        self.status_channel_id = self.bot.settings.report_status_channel

        self.create_log = False

    @property
    def message_id(self):
        # Defining the attribute directly means it doesn't get changed
        # when bot.settings.report_message gets set, this is a work-around
        return self.bot.settings.report_message

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.on_reaction(payload)

    @commands.group(invoke_without_command=True)
    async def report(self, ctx, *, issue=None):
        """Open a report. Parent command for report ticket management."""
        await ctx.invoke(self.report_open, issue=issue)

    @report.command(name='open')
    async def report_open(self, ctx, *, issue=None):
        """Open a report ticket."""
        await self.on_open_command(ctx, issue)

    @report.command(name='openas')
    @is_mod()
    async def report_openas(self, ctx, user: discord.Member, *, issue=None):
        """Help a member by opening a report for them."""
        await self.on_open_command(ctx, issue, user=user)

    @report.command(name='close')
    @ticket_only()
    @is_mod()
    async def report_close(self, ctx, *, reason=None):
        """Close the report. The reason should be a summary."""
        await self.on_close_command(ctx, reason)


def setup(bot):
    bot.add_cog(TicketManager(bot))
    bot.add_cog(ReportManager(bot))
