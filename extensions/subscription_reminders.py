from __future__ import annotations

import asyncio
import datetime
import logging
import zoneinfo
from typing import TYPE_CHECKING, Any, ClassVar

import discord
from asyncpg import BitString
from discord import SelectOption, app_commands
from discord.ext import commands, tasks
from discord.utils import MISSING

from utilities.containers.event_subscription import (
    EventSubConfig,
    MisconfiguredSubscription,
)
from utilities.shared.cache import cache
from utilities.shared.cog import BaseCog
from utilities.shared.converters import WebhookTransformer  # noqa: TCH001
from utilities.shared.ui import BaseView

if TYPE_CHECKING:
    from collections.abc import Coroutine, Sequence
    from typing import Self

    from bot import Graha
    from extensions.fashion_report import FashionReport as FashionReportCog
    from extensions.gates import GATEs
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

    @discord.ui.select(min_values=1, max_values=9)
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
        self.cog.get_sub_config.invalidate(self.cog, interaction.guild.id)

        await interaction.edit_original_response(
            content="Your subscription choices have been recorded, thank you!", view=None
        )


class EventSubscriptions(BaseCog["Graha"], group_name="subscription"):
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
            description="Opt into reminders about Fashion Report check-ins and information from Kaiyoko when available!",
            emoji="\U00002728",
        ),
        discord.SelectOption(
            label="Ocean Fishing",
            value="8",
            description="Opt into reminders about Ocean Fishing expeditions!",
            emoji="\U0001f41f",
        ),
        discord.SelectOption(
            label="Jumbo Cactpot NA",
            value="16",
            description="Opt into reminders about Jumbo Cactpot callouts for NA datacenters.",
            emoji="\U0001f340",
        ),
        discord.SelectOption(
            label="Jumbo Cactpot EU",
            value="32",
            description="Opt into reminders about Jumbo Cactpot callouts for EU datacenters.",
            emoji="\U0001f340",
        ),
        discord.SelectOption(
            label="Jumbo Cactpot JP",
            value="64",
            description="Opt into reminders about Jumbo Cactpot callouts for JP datacenters.",
            emoji="\U0001f340",
        ),
        discord.SelectOption(
            label="Jumbo Cactpot OCE",
            value="128",
            description="Opt into reminders about Jumbo Cactpot callouts for OCE datacenters.",
            emoji="\U0001f340",
        ),
        discord.SelectOption(
            label="GATEs",
            value="256",
            description="Opt into reminders about GATE events opening.",
            emoji="\U0001f3b2",
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
        self.gate_loop.start()

    async def cog_unload(self) -> None:
        self.daily_reset_loop.cancel()
        self.weekly_reset_loop.cancel()
        self.fashion_report_loop.cancel()
        self.ocean_fishing_loop.cancel()
        self.jumbo_cactpot_loop.cancel()
        self.gate_loop.cancel()

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

        subscription_bits = BitString.from_int(subscription_value, length=10)
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
                """
        # webhooks are cascade delete

        LOGGER.info("[EventSub] -> [Delete] :: From guild: %r", config.guild_id)

        await self.bot.pool.execute(query, config.guild_id)

        self.get_sub_config.invalidate(self, config.guild_id)

    @cache(ignore_kwargs=True)
    async def get_sub_config(self, guild_id: int, *, webhook: discord.Webhook | None = None) -> EventSubConfig:
        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE guild_id = $1;
                """

        record: SubscriptionEventRecord | None = await self.bot.pool.fetchrow(query, guild_id)  # type: ignore # wish I knew how to make a Record subclass

        if not record:
            LOGGER.info("[EventSub] -> [Create] :: Creating new subscription config for guild: %s", guild_id)
            if webhook:
                return EventSubConfig.with_webhook(self.bot, guild_id=guild_id, webhook=webhook)
            return EventSubConfig(self.bot, guild_id=guild_id)

        return EventSubConfig.from_record(self.bot, record=record)

    async def _resolve_webhook_from_cache(
        self, config: EventSubConfig, *, log_key: str = "[General Access]"
    ) -> discord.Webhook | None:
        try:
            wh = await config.get_webhook()
        except MisconfiguredSubscription:
            LOGGER.error("[EventSub] -> [Delete] %s :: Subscription %r is misconfigured. Deleting.", log_key, config)
            await self._delete_subscription(config)
            return

        return wh

    @commands.Cog.listener()
    async def on_guild_leave(self, guild: discord.Guild) -> None:
        config = await self.get_sub_config(guild.id)

        await config.delete()
        self.get_sub_config.invalidate(self, guild.id)

    @app_commands.command(name="select")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True, manage_webhooks=True)
    @app_commands.describe(webhook="The existing webhook you wish for me to use for notifications.")
    async def select_subscriptions(
        self, interaction: Interaction, webhook: app_commands.Transform[discord.Webhook, WebhookTransformer] | None = None
    ) -> None:
        """Open a selection of subscriptions for this channel!"""
        assert interaction.guild  # guarded in check
        if not isinstance(interaction.channel, (discord.TextChannel, discord.VoiceChannel, discord.Thread)):
            return await interaction.response.send_message(
                "Sorry, but I can't process subscriptions in this channel. Please use a normal text/voice channel or a thread."
            )

        await interaction.response.defer()

        config = await self.get_sub_config(interaction.guild.id, webhook=webhook)

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

    @app_commands.command(name="change-channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True, manage_webhooks=True)
    @app_commands.describe(channel="The channel to redirect the webhook posts to.")
    async def update_webhook_channel(self, interaction: Interaction, channel: discord.TextChannel) -> None: ...

    async def dispatcher(
        self,
        *,
        webhook: discord.Webhook,
        embeds: Sequence[discord.Embed],
        content: str = MISSING,
        config: EventSubConfig,
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

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(1, length=10))  # type: ignore # reee

        if not records:
            LOGGER.warning("[EventSub] -> [DailyReset] :: No subscriptions. Exiting.")
            return

        resets_cog: ResetsCog | None = self.bot.get_cog("Reset Information")  # type: ignore # ree

        if not resets_cog:
            LOGGER.error("[EventSub] -> [DailyReset] :: Resets cog is not available.")
            return

        embed = resets_cog._get_daily_reset_embed()

        to_send: list[Coroutine[Any, Any, None]] = []
        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            webhook = await self._resolve_webhook_from_cache(conf, log_key="[(DailyReset)]")

            if not webhook:
                continue

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

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(2, length=10))  # type: ignore # reee

        if not records:
            LOGGER.warning("[EventSub] -> [WeeklyReset] :: No subscriptions. Exiting.")
            return

        resets_cog: ResetsCog | None = self.bot.get_cog("Reset Information")  # type: ignore # ree

        if not resets_cog:
            LOGGER.error("[EventSub] -> [WeeklyReset] :: Resets cog is not available.")
            return

        embed = resets_cog._get_weekly_reset_embed()

        to_send: list[Coroutine[Any, Any, None]] = []
        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            webhook = await self._resolve_webhook_from_cache(conf, log_key="[(WeeklyReset)]")

            if not webhook:
                continue

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

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(4, length=10))  # type: ignore # stub shenanigans
        if not records:
            LOGGER.warning("[EventSub] -> [FashionReport] :: No subscriptions. Exiting.")
            return

        fashion_report_cog: FashionReportCog = self.bot.get_cog("FashionReport")  # type: ignore # weird

        fmt: str = MISSING

        fashion_report_cog._reset_state(dt=now + datetime.timedelta(minutes=30))
        await fashion_report_cog._report_task
        embed = fashion_report_cog.generate_fashion_embed()

        to_send: list[Coroutine[Any, Any, None]] = []

        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            webhook = await self._resolve_webhook_from_cache(conf, log_key="[(FashionReport)]")

            if not webhook:
                continue

            embeds = [embed] if embed else []
            to_send.append(self.dispatcher(webhook=webhook, embeds=embeds, content=fmt, config=conf))

        await self.handle_dispatch(to_send)

    @tasks.loop(hours=2)
    async def ocean_fishing_loop(self) -> None:
        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(8, length=10))  # type: ignore
        if not records:
            LOGGER.warning("[EventSub] -> [OceanFishing] :: No subscriptions. Exiting.")
            return

        ocean_fishing_cog: OceanFishingCog | None = self.bot.get_cog("OceanFishing")  # type: ignore
        if not ocean_fishing_cog:
            LOGGER.error("[EventSub] -> [Ocean Fishing] :: No ocean fishing cog available.")
            return

        now = datetime.datetime.now(datetime.UTC)
        embeds = ocean_fishing_cog._generate_both_embeds(now)

        to_send: list[Coroutine[Any, Any, None]] = []
        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            webhook = await self._resolve_webhook_from_cache(conf, log_key="[(OceanFishing)]")

            if not webhook:
                continue

            to_send.append(
                self.dispatcher(
                    content="You can view Lulu's helpful tools on Ocean Fishing data [here](https://ffxiv.pf-n.co/ocean-fishing)!",
                    webhook=webhook,
                    embeds=embeds,
                    config=conf,
                )
            )

        await self.handle_dispatch(to_send)

    @tasks.loop(
        time=[
            datetime.time(hour=0, minute=45, tzinfo=zoneinfo.ZoneInfo("America/Los_Angeles")),
            datetime.time(hour=3, minute=45, tzinfo=zoneinfo.ZoneInfo("America/Los_Angeles")),
            datetime.time(hour=10, minute=45, tzinfo=zoneinfo.ZoneInfo("America/Los_Angeles")),
            datetime.time(hour=17, minute=45, tzinfo=zoneinfo.ZoneInfo("America/Los_Angeles")),
        ]
    )
    async def jumbo_cactpot_loop(self) -> None:
        now = datetime.datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles"))
        if now.weekday() != 5:  # saturday
            LOGGER.warning("[EventSub] -> [Jumbo Cactpot] :: Tried to run on a non-Saturday.")
            return

        # we need to get the Cog first here to calculate the next occurring cactpot loot
        resets: ResetsCog | None = self.bot.get_cog("Reset Information")  # type: ignore # cog downcasting
        if not resets:
            LOGGER.error("[EventSub] -> [Jumbo Cactpot] :: Could not load the resets Cog.")
            return

        region, bitstring_value = resets._get_next_datacenter_cactpot_data(now)
        embed = resets._get_cactpot_embed(region)

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(
            query, BitString.from_int(bitstring_value, length=10)
        )  # type: ignore # stub shenanigans

        if not records:
            LOGGER.warning("[EventSub] -> [JumboCactpot] :: No subscriptions. Exiting.")
            return

        to_send: list[Coroutine[Any, Any, None]] = []

        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            webhook = await self._resolve_webhook_from_cache(conf, log_key="[EventSub] -> [Delete]")

            if not webhook:
                continue

            to_send.append(self.dispatcher(embeds=[embed], webhook=webhook, config=conf))

        await self.handle_dispatch(to_send)

    @tasks.loop(minutes=20)
    async def gate_loop(self) -> None:
        now = datetime.datetime.now(datetime.UTC)

        query = """
                SELECT *
                FROM event_remind_subscriptions
                WHERE subscriptions & $1 = $1;
                """

        records: list[SubscriptionEventRecord] = await self.bot.pool.fetch(query, BitString.from_int(256, length=10))  # type: ignore # stub shenanigans

        if not records:
            LOGGER.warning("[EventSub] -> [GATEs] :: No subscriptions. Exiting.")
            return

        gates_cog: GATEs | None = self.bot.get_cog("GATEs")  # type: ignore # cog downcasting
        if not gates_cog:
            LOGGER.error("[EventSub] -> [GATEs] :: Could not load the GATEs cog.")
            return

        embed = gates_cog.generate_gate_embed(now)

        to_send: list[Coroutine[Any, Any, None]] = []

        for record in records:
            conf = await self.get_sub_config(record["guild_id"])
            webhook = await self._resolve_webhook_from_cache(conf, log_key="([GATEs])")

            if not webhook:
                continue

            to_send.append(self.dispatcher(webhook=webhook, embeds=[embed], config=conf))

        await self.handle_dispatch(to_send)

    @gate_loop.before_loop
    async def before_gate_loop(self) -> None:
        await self.bot.wait_until_ready()

        gate_cog: GATEs | None = self.bot.get_cog("GATEs")  # type: ignore # cog downcasting
        if not gate_cog:
            LOGGER.error("[EventSub] -> [Pre-GATEs] :: Can't load the cog. Cancelling loop.")
            self.gate_loop.cancel()
            return

        next_iter = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=10)
        next_time, _ = gate_cog._resolve_next_gate(dt=next_iter)
        next_time -= datetime.timedelta(minutes=10)

        LOGGER.info("[EventSub] -> [Pre-GATEs] :: Sleeping until %s", next_time)
        await discord.utils.sleep_until(next_time)
        LOGGER.info("[EventSub] -> [Pre-GATEs] :: Woke up at %s", datetime.datetime.now(datetime.UTC))

    @ocean_fishing_loop.before_loop
    async def ocean_fishing_before_loop(self) -> None:
        await self.bot.wait_until_ready()

        now = datetime.datetime.now(datetime.UTC)
        then = now + datetime.timedelta(hours=1) if now.hour % 2 == 0 else now

        if then.minute >= 45:
            # exceeded warning time, alert on next
            then += datetime.timedelta(hours=2)
        then = then.replace(minute=45, second=0, microsecond=0)

        LOGGER.info("[EventSub] -> [OceanFishing] :: Sleeping until %s", then)
        await discord.utils.sleep_until(then)
        LOGGER.info("[EventSub] -> [OceanFishing] :: Woken up at %s", then)

    @jumbo_cactpot_loop.before_loop
    @weekly_reset_loop.before_loop
    @daily_reset_loop.before_loop
    @fashion_report_loop.before_loop
    async def before_loop(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Graha) -> None:
    # Currently we want a slash here, so no guild passed.
    await bot.add_cog(EventSubscriptions(bot))
