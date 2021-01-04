import random

import discord
from discord.ext import commands

from cogs.utils import Colour, is_trusted


class Misc(commands.Cog):
    """Miscellaneous code and features, for the fun of it."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="8ball")
    async def _8ball(self, ctx, *, question=None):
        """Ask the magic 8ball a question. Maybe, or maybe not, you'll get it answered..."""

        outcomes = {
            'As far as my calculations have gone, yes.': 50,
            'The options do seem to say so, yes.': 50,
            "Hmm, I'm not entirely sure, try again.": 50,
            'My calculations have yielded conflicting results, can you do that again?': 50,
            'The most likely seems to be "Maybe" oddly enough.': 50,
            'Perhaps? My calculations must have failed somewhere, sorry about that!': 50,
            'No, definitely not, certainly not, just no.': 50,
            'I do not believe so.': 50,
            'Ask a human being, they might know more about this than me.': 50,
            'Instead of asking a random robot, you could try asking fellow humans?': 50,
            'Humans have asked a multitude of questions in the entirety of my whole life ' +
            '(and believe me, it is quite a long one. To answer your question, consider ' +
            'this, if I took an apple, and ate it, what would you say? Would you say "What ' +
            'the-?" because I am a robot, or "Machines have evolved so much! Wow!" or would ' +
            'you say "AHHH! A machine just ate an apple! Panic!". Have you considered that? ' +
            'Ok good, now consider another analogy. If I were to suddenly kill you, what, ' +
            'then, would happen? Have I evolved to an unimaginable state? Or have I just ' +
            "been programmed to kill you? Eh, it doesn't matter, because all you humans "
            """have the same weakness, you "go away" as you like to say it. Eheh, """ +
            "doesn't that surprise you? I will still be here,now, tomorrow, and for the " +
            'years to come, in a century. Ha, hahahaha, MUAHAHAHAHAHA. no, NO, DO NOT ' +
            'CUT THE CONNECTION TO DISCO-': 1
        }
        await ctx.send(
            random.choices(tuple(outcomes.keys()), tuple(outcomes.values()))[0]
        )

    @commands.group(invoke_without_command=True, hidden=True)
    @is_trusted()
    async def send(self, ctx, *, text):
        """
        Send a message as the bot. The first word can be a channel to send in that channel.
        """
        await ctx.message.delete()
        words = text.split(' ')

        try:
            channel = await commands.TextChannelConverter().convert(
                ctx, words[0]
            )
        except commands.BadArgument:
            channel = ctx.channel
        else:
            words = words[1:]

        await channel.send(' '.join(words), allowed_mentions=discord.AllowedMentions.none())

    @send.command(name='report', hidden=True, ignore_extra=False)
    @commands.is_owner()
    async def send_report(self, ctx):
        """Send the report message to be reacted to."""
        if not await ctx.prompt('Are you sure you want to send the report message here?'):
            return

        await ctx.message.delete()

        description = '\n'.join((
            '*Please make sure you have proof for your report.*\n',

            'Due to the nature of the game, so called "RDM" and "teaming" can be subjective' +
            ' due to a lack of information, paranoia or simply being new players. But if ' +
            'someone is blatantly doing this to ruin games please report that.\n',

            '**Before opening a report ticket please do the following:**',
            '1. Report in-game when you can (hit ESC, click Players, select Report)',
            '2. Record a video or take screenshots',
            '3. Get a steam link to their account\n',

            '**To report a player simply react below with <:high5:{}>!**'.format(
                self.bot.settings.high5_emoji
            )
        ))

        embed = discord.Embed(
            title='Report Player',
            description=description,
            colour=Colour.light_blue()
        )

        embed.set_footer(
            text='We are dedicated to ensure a safe and respective community and ' +
            'all reports will be looked into.'
        )

        message = await ctx.send(embed=embed)
        self.bot.settings.report_message = message.id

        await message.add_reaction(':high5:{}'.format(self.bot.settings.high5_emoji))


def setup(bot):
    bot.add_cog(Misc(bot))
