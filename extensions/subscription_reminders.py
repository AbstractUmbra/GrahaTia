from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, ClassVar

import discord
import pendulum
from asyncpg import BitString
from discord import SelectOption, app_commands
from discord.ext import tasks
from discord.utils import MISSING

from utilities.cache import cache
from utilities.cog import GrahaBaseCog
from utilities.containers.event_subscription import EventSubConfig, MisconfiguredSubscription
from utilities.context import Interaction
from utilities.formats import format_dt
from utilities.ui import GrahaBaseView


if TYPE_CHECKING:
    from typing_extensions import Self

    from bot import Graha
    from extensions.fashion_report import FashionReport as FashionReportCog
    from utilities._types.xiv.record_aliases.subscription import EventRecord as SubscriptionEventRecord

LOGGER = logging.getLogger(__name__)


class NoKaiyokoPost(Exception):
    pass


class EventSubView(GrahaBaseView):
    def __init__(self, *, timeout: float | None = 180.0, options: list[SelectOption]) -> None:
        super().__init__(timeout=timeout)
        self.sub_selection.options = options

    async def on_timeout(self) -> None:
        return

    @discord.ui.select(max_values=5, min_values=1)  # type: ignore # pyright bug
    async def sub_selection(self, interaction: Interaction, item: discord.ui.Select[Self]) -> None:
        await interaction.response.edit_message(
            content="Thank you, your subscription choices have been recorded!", view=None
        )
        self.stop()


class EventSubscriptions(GrahaBaseCog, group_name="subscription"):
    POSSIBLE_SUBSCRIPTIONS: ClassVar[list[discord.SelectOption]] = [
        discord.SelectOption(
            label="Daily Resets", value="1", description="Opt into reminders about daily resets!", emoji="\U0001f4bf"
        ),
        discord.SelectOption(
            label="Weekly Resets", value="2", description="Opt into reminders about weekly resets!", emoji="\U0001f4c0"
        ),
        discord.SelectOption(
            label="Fashion Report",
            value="4",
            description="Opt into reminders about Fashion Report check-in!",
            emoji="\U00002728",
        ),
        discord.SelectOption(
            label="Ocean Fishing",
            value="8",
            description="Opt into reminders about Ocean Fishing expeditions!",
            emoji="\U0001f41f",
        ),
        discord.SelectOption(
            label="Jumbo Cactpot",
            value="16",
            description="Opt into reminders about Jumbo Cactpot callouts.",
            emoji="\U0001f340",
        ),
    ]
    __cog_is_app_commands_group__ = True

    def __init__(self, bot: Graha, /) -> None:
        self.bot: Graha = bot
        # self.daily_reset_loop.start()
        # self.weekly_reset_loop.start()
        self.fashion_report_loop.start()
        # self.ocean_fishing_loop.start()
        self.jumbo_cactpot_loop.start()

    async def cog_unload(self) -> None:
        # self.daily_reset_loop.stop()
        # self.weekly_reset_loop.stop()
        self.fashion_report_loop.stop()
        # self.ocean_fishing_loop.stop()
        self.jumbo_cactpot_loop.stop()

    async def _set_subscriptions(
        self,
        guild_id: int,
        subscription_value: int,
        webhook_url: str | None,
        channel_id: int | None = None,
        thread_id: int | None = None,
    ) -> None:
        query = """
                INSERT INTO event_remind_subscriptions (guild_id, webhook_url, subscriptions, channel_id, thread_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id)
                DO UPDATE SET
                    webhook_url = EXCLUDED.webhook_url,
                    subscriptions = EXCLUDED.subscriptions,
                    channel_id = EXCLUDED.channel_id,
                    thread_id = EXCLUDED.thread_id;
                """

        subscription_bits = BitString.from_int(subscription_value, length=10)
        await self.bot.pool.execute(query, guild_id, webhook_url, subscription_bits, channel_id, thread_id)
        self.get_sub_config.invalidate(self, guild_id)

    async def _delete_subscription(self, config: EventSubConfig) -> None:
        query = """
                DELETE FROM event_remind_subscriptions
                WHERE guild_id = $1
                CASCADE;
                """

        await self.bot.pool.execute(query, config.guild_id)

        self.get_sub_config.invalidate(self, config.guild_id)

    @cache()
    async def get_sub_config(self, guild_id: int) -> EventSubConfig:
        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE guild_id = $1;
                """

        record: SubscriptionEventRecord | None = await self.pool.fetchrow(query, guild_id)  # type: ignore # wish I knew how to make a Record subclass

        if not record:
            return EventSubConfig(self.bot, guild_id=guild_id)

        return EventSubConfig.from_record(self.bot, record=record)

    @app_commands.command(name="select")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True, manage_webhooks=True)
    async def select_subscriptions(self, interaction: Interaction) -> None:
        """Open a selection of subscriptions for this channel!"""
        assert interaction.guild  # guarded in check
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                "Sorry, but I can't process subscriptions in this channel. Please use a normal text channel or a thread."
            )

        await interaction.response.defer()

        config = await self.get_sub_config(interaction.guild.id)

        options = self.POSSIBLE_SUBSCRIPTIONS[:]

        for (_, value), option in zip(config.subscriptions, options):
            option.default = value

        view = EventSubView(options=options)
        await interaction.followup.send(view=view)
        await view.wait()

        resolved_flags = sum(map(int, view.sub_selection.values))

        webhook = None
        channel_id = None
        thread_id = None

        if isinstance(interaction.channel, discord.Thread):
            current_channel = interaction.channel.parent
        else:
            current_channel = interaction.channel

        assert current_channel  # this should never happen

        try:
            webhook = await config._resolve_webhook(force=False)
        except discord.HTTPException:
            await interaction.followup.send(
                "I was not able to create the necessary webhook. Can you please correct my permissions and try again?"
            )
            return

        if isinstance(interaction.channel, discord.Thread) and isinstance(interaction.channel.parent, discord.TextChannel):
            channel_id = interaction.channel.parent.id
            thread_id = interaction.channel.id

        await self._set_subscriptions(interaction.guild.id, resolved_flags, (webhook and webhook.url), channel_id, thread_id)

    @select_subscriptions.error
    async def on_subscription_select_error(self, interaction: Interaction, error: app_commands.AppCommandError) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=False)

        await interaction.followup.send("Sorry, there was an error processing this command!")

    @tasks.loop(time=datetime.time(hour=14, minute=45, tzinfo=datetime.timezone.utc))
    async def daily_reset_loop(self) -> None:
        ...

    @daily_reset_loop.before_loop
    async def daily_reset_before_loop(self) -> None:
        now = pendulum.now()
        if now.hour > 7:
            if now.minute > 45:
                then = now.next()
        then = now

        sleep_until = datetime.datetime.combine(
            then, datetime.time(hour=7, minute=45, second=0, microsecond=0), tzinfo=datetime.timezone.utc
        )

        LOGGER.info("[Subscriptions] :: Daily Reset sleeping until %s", sleep_until)

        await discord.utils.sleep_until(sleep_until)

    @tasks.loop(time=datetime.time(hour=7, minute=45, tzinfo=datetime.timezone.utc))
    async def weekly_reset_loop(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now.weekday() != 1:  # tuesday
            return

        ...

    @weekly_reset_loop.before_loop
    async def weekly_reset_before_loop(self) -> None:
        now = pendulum.now()
        if now.weekday() != 1:
            then = now.next(2)
        else:
            then = now

        sleep_until = datetime.datetime.combine(
            then, datetime.time(hour=7, minute=45, second=0, microsecond=0), tzinfo=datetime.timezone.utc
        )

        LOGGER.info("[Subscriptions] :: Weekly Reset sleeping until %s", sleep_until)

        await discord.utils.sleep_until(sleep_until)

    @tasks.loop(time=datetime.time(hour=7, tzinfo=datetime.timezone.utc))
    async def fashion_report_loop(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now.weekday() != 4:  # friday
            return

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(4, length=6))  # type: ignore # stub shenanigans

        fashion_report_cog: FashionReportCog = self.bot.get_cog("FashionReport")  # type: ignore # weird

        fmt: str = MISSING

        try:
            embed = await fashion_report_cog._gen_fashion_embed()
        except ValueError:
            # no report yet.
            fmt = "Kaiyoko's post is not up yet. Please use `g fr` later for their insight!"
            embed = MISSING

        for record in records:
            conf = await self.get_sub_config(existing_record=record)
            try:
                webhook = await conf.get_webhook()
            except MisconfiguredSubscription:
                LOGGER.warn("Subscription %r is misconfigured. Deleting.", conf)
                # todo: resolve a way to let people know it was messed up.
                await self._delete_subscription(conf)
                return

            if not webhook:
                webhook = await conf._resolve_webhook(force=True)

            await webhook.send(fmt, embed=embed, thread=conf.thread)

    @fashion_report_loop.before_loop
    async def fashion_report_before_loop(self) -> None:
        now = pendulum.now()
        if now.weekday() != 4:
            then = now.next(5)
        else:
            then = now

        sleep_until = datetime.datetime.combine(
            then, datetime.time(hour=7, minute=45, second=0, microsecond=0), tzinfo=datetime.timezone.utc
        )

        LOGGER.info("[Subscriptions] :: Fashion Report sleeping until %s", sleep_until)

        await discord.utils.sleep_until(sleep_until)

    @tasks.loop(hours=2)
    async def ocean_fishing_loop(self) -> None:
        ...

    @ocean_fishing_loop.before_loop
    async def ocean_fishing_before_loop(self) -> None:
        # todo calculate odd-hour 45m cycle to sleep.
        ...

    @tasks.loop(time=datetime.time(hour=18, minute=45, tzinfo=datetime.timezone.utc))
    async def jumbo_cactpot_loop(self) -> None:
        now = datetime.datetime.now(datetime.timezone.utc)
        if now.weekday() != 1:  # tuesday
            return

        then = (now + datetime.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        embed = discord.Embed(
            title="Jumbo Cactpot!", description=f"The Jumbo Cactpot numbers will be called in {format_dt(then):R}!"
        )

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(4, length=6))  # type: ignore # stub shenanigans

        for record in records:
            conf = EventSubConfig.from_record(self.bot, record=record)
            webhook = await conf.get_webhook()

            await webhook.send(embed=embed, thread=conf.thread)

    @jumbo_cactpot_loop.before_loop
    async def jumbo_cactpot_before_loop(self) -> None:
        now = pendulum.now()
        if now.weekday() != 5:
            then = now.next(6)
        else:
            then = now

        sleep_until = datetime.datetime.combine(
            then, datetime.time(hour=18, minute=45, second=0, microsecond=0), tzinfo=datetime.timezone.utc
        )

        LOGGER.info("[Subscriptions] :: Jumbo Cactpot sleeping until %s", sleep_until)

        await discord.utils.sleep_until(sleep_until)


async def setup(bot: Graha) -> None:
    # Currently we want a slash here, so no guild passed.
    await bot.add_cog(EventSubscriptions(bot))
