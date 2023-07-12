from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import discord
from discord import SelectOption, app_commands

from utilities.cog import GrahaBaseCog
from utilities.context import Interaction
from utilities.ui import GrahaBaseView


if TYPE_CHECKING:
    from typing_extensions import Self

    from bot import Graha
    from utilities.containers.event_subscription import EventSubConfig


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

    async def _resolve_webhook(self, config: EventSubConfig, *, force: bool) -> discord.Webhook:
        webhook = config.webhook
        if not webhook:
            return await self._create_or_replace_webhook(config, force=force)

        return webhook

    async def _create_or_replace_webhook(self, config: EventSubConfig, *, force: bool = False) -> discord.Webhook:
        if force:
            # we just delete the old and create the new
            if config.webhook:
                try:
                    await config.webhook.delete(reason="Forced deletion by G'raha Tia. Re-creating.")
                except discord.HTTPException:
                    pass

        assert config.channel  # guarded before getting here.
        webhook = await config.channel.create_webhook(name="XIV Timers", reason="Created via G'raha Tia subscriptions!")
        query = """
                UPDATE event_remind_subscriptions
                SET webhook_url = $2
                WHERE guild_id = $1;
                """
        await self.bot.pool.execute(query, config.guild_id, webhook.url)

        return webhook

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

        await self.bot.pool.execute(query, guild_id, webhook_url, subscription_value, channel_id, thread_id)

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

        config = await interaction.client.get_sub_config(interaction.guild.id)

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
            webhook = await self._resolve_webhook(config, force=False)
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


async def setup(bot: Graha) -> None:
    # Currently we want a slash here, so no guild passed.
    await bot.add_cog(EventSubscriptions(bot))
