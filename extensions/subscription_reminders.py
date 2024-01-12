from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Any, ClassVar

import discord
from asyncpg import BitString
from discord import SelectOption, app_commands
from discord.ext import commands, tasks
from discord.utils import MISSING

from utilities.cog import GrahaBaseCog
from utilities.containers.event_subscription import (
    EventSubConfig,
    MisconfiguredSubscription,
)
from utilities.shared.cache import cache
from utilities.shared.ui import BaseView

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence
    from typing import Self

    from bot import Graha
    from extensions.fashion_report import FashionReport as FashionReportCog
    from extensions.ocean_fishing import OceanFishing as OceanFishingCog
    from extensions.resets import Resets as ResetsCog
    from utilities.context import Interaction
    from utilities.shared._types.xiv.record_aliases.subscription import (
        EventRecord as SubscriptionEventRecord,
    )

LOGGER = logging.getLogger(__name__)


class NoKaiyokoPost(Exception):
    pass


class EventSubView(BaseView):
    def __init__(self, *, timeout: float | None = 180.0, options: list[SelectOption], cog: EventSubscriptions) -> None:
        super().__init__(timeout=timeout)
        self.sub_selection.options = options
        self.cog: EventSubscriptions = cog

    async def on_timeout(self) -> None:
        return

    @discord.ui.select(max_values=5, min_values=1)  # type: ignore # pyright bug
    async def sub_selection(self, interaction: Interaction, item: discord.ui.Select[Self]) -> None:
        assert interaction.guild  # guarded in earlier check
        await interaction.response.defer()

        config = await self.cog.get_sub_config(interaction.guild.id)

        resolved_flags = sum(map(int, self.sub_selection.values))

        if isinstance(interaction.channel, discord.Thread):
            current_channel = interaction.channel.parent
        else:
            current_channel = interaction.channel

        assert current_channel  # this should never happen
        config.channel_id = current_channel.id

        if isinstance(interaction.channel, discord.Thread) and isinstance(interaction.channel.parent, discord.TextChannel):
            channel_id = interaction.channel.parent.id
            thread_id = interaction.channel.id
        else:
            channel_id = current_channel.id
            thread_id = None

        await self.cog._set_subscriptions(interaction.guild.id, resolved_flags, channel_id, thread_id)

        await interaction.edit_original_response(
            content="Your subscription choices have been recorded, thank you!", view=None
        )


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
        self.avatar_url: str = "https://static.abstractumbra.dev/images/graha.png"
        self.daily_reset_loop.start()
        self.weekly_reset_loop.start()
        self.fashion_report_loop.start()
        self.ocean_fishing_loop.start()
        self.jumbo_cactpot_loop.start()

    async def cog_unload(self) -> None:
        self.daily_reset_loop.cancel()
        self.weekly_reset_loop.cancel()
        self.fashion_report_loop.cancel()
        self.ocean_fishing_loop.cancel()
        self.jumbo_cactpot_loop.cancel()

    async def _set_subscriptions(
        self,
        guild_id: int,
        subscription_value: int,
        channel_id: int | None = None,
        thread_id: int | None = None,
    ) -> None:
        query = """
                INSERT INTO event_remind_subscriptions
                    (guild_id, subscriptions, channel_id, thread_id)
                VALUES
                    ($1, $2, $3, $4)
                ON CONFLICT
                    (guild_id)
                DO UPDATE SET
                    subscriptions = EXCLUDED.subscriptions,
                    channel_id = EXCLUDED.channel_id,
                    thread_id = EXCLUDED.thread_id;
                """

        subscription_bits = BitString.from_int(subscription_value, length=6)
        await self.bot.pool.execute(
            query,
            guild_id,
            subscription_bits,
            channel_id,
            thread_id,
        )
        config = await self.get_sub_config(guild_id)
        webhook = await config.get_webhook()

        webhook_query = """
                        WITH sub_update AS (
                            UPDATE event_remind_subscriptions
                                SET webhook_id = $1
                                WHERE guild_id = $2
                            RETURNING guild_id
                        )
                        INSERT INTO webhooks
                            (guild_id, webhook_id, webhook_url, webhook_token)
                        SELECT
                            sub_update.guild_id, $1, $3, $4
                        FROM sub_update
                        ON CONFLICT
                            (guild_id)
                        DO UPDATE SET
                            webhook_id = EXCLUDED.webhook_id,
                            webhook_url = EXCLUDED.webhook_url,
                            webhook_token = EXCLUDED.webhook_token;
                        """
        await self.bot.pool.execute(webhook_query, webhook.id, guild_id, webhook.url, webhook.token)

        self.get_sub_config.invalidate(self, guild_id)

    async def _delete_subscription(self, config: EventSubConfig) -> None:
        query = """
                DELETE FROM event_remind_subscriptions
                WHERE guild_id = $1;
                DELETE FROM webhooks
                WHERE guild_id = $1;
                """

        LOGGER.info("[EventSub] -> [Delete] :: From guild: %r", config.guild_id)

        await self.bot.pool.execute(query, config.guild_id)

        self.get_sub_config.invalidate(self, config.guild_id)

    @cache()
    async def get_sub_config(self, guild_id: int) -> EventSubConfig:
        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE guild_id = $1;
                """

        record: SubscriptionEventRecord | None = await self.bot.pool.fetchrow(query, guild_id)  # type: ignore # wish I knew how to make a Record subclass

        if not record:
            LOGGER.info("[EventSub] -> [Create] :: Creating new subscription config for guild: %s", guild_id)
            return EventSubConfig(self.bot, guild_id=guild_id)

        return EventSubConfig.from_record(self.bot, record=record)

    @commands.Cog.listener()
    async def on_guild_leave(self, guild: discord.Guild) -> None:
        config = await self.get_sub_config(guild.id)

        await config.delete()
        self.get_sub_config.invalidate(self, guild.id)

    @app_commands.command(name="select")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True, manage_webhooks=True)
    async def select_subscriptions(self, interaction: Interaction) -> None:
        """Open a selection of subscriptions for this channel!"""
        assert interaction.guild  # guarded in check
        if not isinstance(interaction.channel, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            return await interaction.response.send_message(
                "Sorry, but I can't process subscriptions in this channel. Please use a normal text channel or a thread."
            )

        await interaction.response.defer()

        config = await self.get_sub_config(interaction.guild.id)

        options = self.POSSIBLE_SUBSCRIPTIONS[:]

        for (_, value), option in zip(config.subscriptions, options):
            option.default = value

        view = EventSubView(options=options, cog=self)
        await interaction.followup.send(
            content="Please select which reminders you wish to recieve in the following dropdown!", view=view
        )

    @select_subscriptions.error
    async def on_subscription_select_error(self, interaction: Interaction, error: app_commands.AppCommandError) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=False)

        await interaction.followup.send("Sorry, there was an error processing this command!")

    async def dispatcher(
        self, *, webhook: discord.Webhook, embeds: Sequence[discord.Embed], content: str = MISSING, config: EventSubConfig
    ) -> None:
        try:
            await webhook.send(content=content, embeds=embeds, thread=config.thread, avatar_url=self.avatar_url)
        except (discord.NotFound, MisconfiguredSubscription):
            await self._delete_subscription(config)

    async def handle_dispatch(self, to_dispatch: list[Coroutine[Any, Any, None]]) -> None:
        await asyncio.gather(*to_dispatch, return_exceptions=False)

        # TODO handle exceptions cleanly?

    @tasks.loop(time=datetime.time(hour=14, minute=45, tzinfo=datetime.UTC))
    async def daily_reset_loop(self) -> None:
        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(1, length=6))  # type: ignore # reee

        if not records:
            return

        resets_cog: ResetsCog | None = self.bot.get_cog("Reset Information")  # type: ignore # ree

        if not resets_cog:
            LOGGER.error("[EventSub] -> [DailyReset] :: Resets cog is not available.")
            return

        embed = resets_cog._get_daily_reset_embed()

        to_send: list[Coroutine[Any, Any, None]] = []
        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            try:
                webhook = await conf.get_webhook()
            except MisconfiguredSubscription:
                LOGGER.warning("[EventSub] -> [Delete] ([DailyReset]) :: Subscription %r is misconfigured. Deleting.", conf)
                await self._delete_subscription(conf)
                return

            to_send.append(self.dispatcher(webhook=webhook, embeds=[embed], config=conf))

        await self.handle_dispatch(to_send)

    @tasks.loop(time=datetime.time(hour=7, minute=45, tzinfo=datetime.UTC))
    async def weekly_reset_loop(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        if now.weekday() != 1:  # tuesday
            LOGGER.warning(
                "[EventSub] -> [Weekly reset] :: Attempted to run on a non-Tuesday: '%s (day # '%s')'",
                now.strftime("%A"),
                now.weekday(),
            )
            return

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(2, length=6))  # type: ignore # reee

        if not records:
            LOGGER.info("[EventSub] -> [Weekly reset] :: No records found to notify.")
            return

        resets_cog: ResetsCog | None = self.bot.get_cog("Reset Information")  # type: ignore # ree

        if not resets_cog:
            LOGGER.error("[EventSub] -> [Weekly reset] :: Resets cog is not available.")
            return

        embed = resets_cog._get_weekly_reset_embed()

        to_send: list[Coroutine[Any, Any, None]] = []
        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            try:
                webhook = await conf.get_webhook()
            except MisconfiguredSubscription:
                LOGGER.warning("[EventSub] -> [Delete] ([WeeklyReset]) :: Subscription %r is misconfigured. Deleting.", conf)
                await self._delete_subscription(conf)
                return

            to_send.append(self.dispatcher(webhook=webhook, embeds=[embed], config=conf))

        await self.handle_dispatch(to_send)

    @tasks.loop(time=datetime.time(hour=7, minute=45, tzinfo=datetime.UTC))
    async def fashion_report_loop(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        if now.weekday() != 4:  # friday
            return

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(4, length=6))  # type: ignore # stub shenanigans
        if not records:
            return

        fashion_report_cog: FashionReportCog = self.bot.get_cog("FashionReport")  # type: ignore # weird

        fmt: str = MISSING

        try:
            embed = await fashion_report_cog._gen_fashion_embed()
        except ValueError:
            # no report yet.
            fmt = (
                "Kaiyoko's post is not up yet. Please use `gt fr` later for their insight, or have a look on their Twitter"
                " page for the post:-\n<https://twitter.com/KaiyokoStar>"
            )
            embed = MISSING

        to_send: list[Coroutine[Any, Any, None]] = []

        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            try:
                webhook = await conf.get_webhook()
            except MisconfiguredSubscription:
                LOGGER.warning(
                    "[EventSub] -> [Delete] ([FashionReport]) :: Subscription %r is misconfigured. Deleting.", conf
                )
                # todo: resolve a way to let people know it was messed up.
                await self._delete_subscription(conf)
                return

            to_send.append(self.dispatcher(webhook=webhook, embeds=[embed], content=fmt, config=conf))

        await self.handle_dispatch(to_send)

    @tasks.loop(hours=2)
    async def ocean_fishing_loop(self) -> None:
        ocean_fishing_cog: OceanFishingCog | None = self.bot.get_cog("OceanFishing")  # type: ignore
        if not ocean_fishing_cog:
            LOGGER.error("[EventSub] -> [Ocean Fishing] :: No ocean fishing cog available.")
            return

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(8, length=6))  # type: ignore
        if not records:
            return

        now = datetime.datetime.now(datetime.UTC)

        embeds = ocean_fishing_cog._generate_both_embeds(now)

        to_send: list[Coroutine[Any, Any, None]] = []
        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            try:
                webhook = await conf.get_webhook()
            except MisconfiguredSubscription:
                LOGGER.warning(
                    "[EventSub] -> [Delete] ([OceanFishing]) :: Subscription %r is misconfigured. Deleting.", conf
                )
                await self._delete_subscription(conf)
                return

            to_send.append(self.dispatcher(webhook=webhook, embeds=embeds, config=conf))

        await self.handle_dispatch(to_send)

    @tasks.loop(time=datetime.time(hour=18, minute=45, tzinfo=datetime.UTC))
    async def jumbo_cactpot_loop(self) -> None:
        now = datetime.datetime.now(datetime.UTC)
        if now.weekday() != 5:  # saturday
            LOGGER.warning("[EventSub] -> [Jumbo Cactpot] :: Tried to run on a non-Saturday.")
            return

        resets: ResetsCog | None = self.bot.get_cog("Reset Information")  # type: ignore # cog downcasting
        if not resets:
            LOGGER.error("[EventSub] -> [Jumbo Cactpot] :: Could not load the resets Cog.")
            return

        embed = resets._get_cactpot_embed()

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
    @ocean_fishing_loop.before_loop
    @weekly_reset_loop.before_loop
    @daily_reset_loop.before_loop
    @fashion_report_loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Graha) -> None:
    # Currently we want a slash here, so no guild passed.
    await bot.add_cog(EventSubscriptions(bot))
