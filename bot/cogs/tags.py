import asyncpg
from discord.ext import commands

from cogs.utils import is_mod


class TagName(commands.clean_content):
    """A converter to convert the argument to an acceptable tag name."""
    async def convert(self, ctx, argument):
        # Convert it like clean_content, then make lowercase,
        # and also strip leading and trailing spaces.
        converted = (await super().convert(ctx, argument)).lower().strip()

        if not converted:  # Nothing left
            raise commands.BadArgument('Missing tag name.')

        if len(converted) > 50:
            raise commands.BadArgument('Tag name too long, max is 50 characters.')

        # We want to get the first word, to see if it's already a command.
        first_word, _, _ = converted.partition(' ')

        return converted


class Tags(commands.Cog):
    """Tag related management commands."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_content_id(self, name, *, conn=None):
        conn = conn or self.bot.pool

        return await conn.fetchval('SELECT content_id FROM tags WHERE name=$1', name)

    @commands.group(invoke_without_command=True)
    @is_mod()
    async def tag(self, ctx, *, name: TagName):
        """Forcefully send a tag. Parent command for tag management."""
        try:
            await ctx.send_tag(name)
        except commands.CommandNotFound:
            return  # Do nothing, we don't care

    @tag.command(name='create')
    async def tag_create(self, ctx, name: TagName, *, content):
        """Create a new tag and content."""
        try:
            async with ctx.db.acquire() as conn:
                async with conn.transaction():
                    content_id = await self.bot.create_content(content, conn=conn)
                    await self.bot.create_tag(name, content_id, conn=conn)
        except asyncpg.UniqueViolationError:
            await ctx.send('This tag already exists!')
        except Exception:
            await ctx.send('Something went wrong!')
        else:
            await ctx.send('Tag and content successfully created.')

    @tag.command(name='add', aliases=['alias'])
    async def tag_add(self, ctx, name: TagName, alias: TagName):
        """Add a new tag, alias to the content."""
        await ctx.db.acquire()

        content_id = self._get_content_id(name)
        if not content_id:
            return await ctx.send('That is not an existing tag!')

        try:
            await self.bot.create_tag(alias, content_id, conn=ctx.db)
        except asyncpg.UniqueViolationError:
            await ctx.send('This tag/alias already exists!')
        except Exception:
            await ctx.send('Something went wrong!')
        else:
            await ctx.send('Tag successfully created.')

    @tag.command(name='edit')
    async def tag_edit(self, ctx, name: TagName, *, content):
        """Override and edit a tag's content."""
        await ctx.db.acquire()

        content_id = self._get_content_id(name)
        if not content_id:
            return await ctx.send('That is not an existing tag!')

        await ctx.db.execute(
            'UPDATE tag_content SET value=$2 WHERE id=$1', content_id, content
        )

        await ctx.send('Edited tag content.')

    @tag.command(name='remove')
    async def tag_remove(self, ctx, name: TagName):
        """Safely remove a tag, alias. This action keeps the content."""
        prompt = ('Are you sure you want to safely remove this tag? This will keep ' +
                  'the content and other aliases.')
        if not await ctx.prompt(prompt):
            return

        await ctx.acquire()

        # We really don't want to remove the last tag
        content_id = self._get_content_id(name)
        if not content_id:
            return await ctx.send('That is not an existing tag!')

        query = 'SELECT id, name FROM tags WHERE content_id=$2 AND name<>$1 LIMIT 1;'
        other_tag = await ctx.db.fetchrow(query, name, content_id)
        if other_tag:
            # We found another tag, so let's do like told and remove the one specified
            await ctx.db.execute('DELETE FROM tags WHERE name=$1', name)
            await ctx.send(f"Tag removed, but you can still use `{other_tag['name']}`. ")
        else:
            await ctx.send(
                f'This is the last alias to content `#{content_id}`, use `?tag delete`!'
            )

    @tag.command(name='delete')
    async def tag_delete(self, ctx, name: TagName):
        """Delete a tag, its other aliases, and its content."""
        prompt = ("Are you sure you want to completely remove this tags' " +
                  "content and all other aliases?")
        if not await ctx.prompt(prompt):
            return

        await ctx.acquire()

        content_id = self._get_content_id(name)
        if not content_id:
            return await ctx.send('That is not an existing tag!')

        await ctx.db.execute('DELETE FROM tag_content WHERE id=$1;', content_id)

        await ctx.send('This content and all its tags are now fully removed!')


def setup(bot):
    bot.add_cog(Tags(bot))
