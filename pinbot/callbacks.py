import logging
import asyncio

from nio import (
    AsyncClient,
    InviteMemberEvent,
    JoinError,
    MatrixRoom,
    MegolmEvent,
    RoomGetEventError,
    RoomMessageText,
    UnknownEvent,
)

from pinbot.chat_functions import make_pill, react_to_event, send_text_to_room
from pinbot.config import Config
from pinbot.message_responses import Message
from pinbot.storage import Storage

logger = logging.getLogger(__name__)


class Callbacks:
    def __init__(self, client: AsyncClient, store: Storage, config: Config):
        """
        Args:
            client: nio client used to interact with matrix.

            store: Bot storage.

            config: Bot configuration parameters.
        """
        self.client = client
        self.store = store
        self.config = config
        self.command_prefix = config.command_prefix
        self.synced = False
        self.pinned = set()

    async def invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        """Callback for when an invite is received. Join the room specified in the invite.

        Args:
            room: The room that we are invited to.

            event: The invite event.
        """
        logger.debug(f"Got invite to {room.room_id} from {event.sender}.")

        # Attempt to join 3 times before giving up
        for attempt in range(3):
            result = await self.client.join(room.room_id)
            if type(result) == JoinError:
                logger.error(
                    f"Error joining room {room.room_id} (attempt %d): %s",
                    attempt,
                    result.message,
                )
                await asyncio.sleep(1)
            else:
                break
        else:
            logger.error("Unable to join room: %s", room.room_id)

        # Successfully joined room
        logger.info(f"Joined {room.room_id}")

    async def _reaction(
        self, room: MatrixRoom, event: UnknownEvent, reacted_to_id: str
    ) -> None:
        """A reaction was sent to one of our messages. Let's send a reply acknowledging it.

        Args:
            room: The room the reaction was sent in.

            event: The reaction event.

            reacted_to_id: The event ID that the reaction points to.
        """
        logger.debug(f"Got reaction to {room.room_id} from {event.sender}.")
        if not self.synced:
            # we got this reaction while catching up, ignore it
            #logger.warn("Got reaction %s while syncing...", reacted_to_id)
            return

        # don't allow pinning of things in the pin room
        if room.room_id == self.config.pins_room:
            return

        # Get the original event that was reacted to
        event_response = await self.client.room_get_event(room.room_id, reacted_to_id)
        if isinstance(event_response, RoomGetEventError):
            logger.warning(
                "Error getting event that was reacted to (%s)", reacted_to_id
            )
            return
        reacted_to_event = event_response.event
        if isinstance(reacted_to_event, MegolmEvent):
            logger.error(
                "Unable to decrypt event reacted to (%s)", reacted_to_id
            )
            return

        # Ignore our own reactions
        if reacted_to_event.sender == self.config.user_id:
            return
        reaction_emoji = (
            event.source.get("content", {}).get("m.relates_to", {}).get("key")
        )
        # We only care about pin emojis
        if reaction_emoji != "📌":
            return
        # and only pins we haven't already saved
        if reacted_to_id in self.pinned:
            logger.info(
                "Someone tried to pin %s multiple times, ignoring", reacted_to_id
            )
            return

        # Send a message to the pins room, archiving the pinned message
        # the matrix spec is absolute trash
        pinned_sender_pill = make_pill(reacted_to_event.sender)
        logger.info(f"Pinning `{reacted_to_event.body}`")
        fallback_body = reacted_to_event.body.join('\n> ')
        body = (
f"""
> {reacted_to_event.sender[0]} {fallback_body}

Pinned
"""
        )
        # how do the matrix.to URIs work?? the link is useless
        room_slug = room.room_id
        event_slug = reacted_to_id
        quote_body = reacted_to_event.formatted_body if reacted_to_event.formatted_body is not None else reacted_to_event.body
        formatted = (
f"""
<mx-reply>
  <blockquote>
    <a href="https://matrix.to/#/{room_slug}/{event_slug}">Pinned</a>
    {pinned_sender_pill}
    <br />
    <!-- This is where the related event's HTML would be. -->
    {quote_body}
  </blockquote>
</mx-reply>
"""
        )
        # probably gotta escape all this shit huh
        logging.info("Pinning message by %s in %s to %s", pinned_sender_pill, reacted_to_id, self.config.pins_room)
        await self.client.room_send(
            self.config.pins_room,
            "m.room.message",
            {
                "msgtype": "m.text",
                "body": body,
                "format": "org.matrix.custom.html",
                "formatted_body": formatted,
            }, None, False)
        self.pinned.add(reacted_to_id)

    async def decryption_failure(self, room: MatrixRoom, event: MegolmEvent) -> None:
        """Callback for when an event fails to decrypt. Inform the user.

        Args:
            room: The room that the event that we were unable to decrypt is in.

            event: The encrypted event that we were unable to decrypt.
        """
        logger.error(
            f"Failed to decrypt event '{event.event_id}' in room '{room.room_id}'!"
            f"\n\n"
            f"Tip: try using a different device ID in your config file and restart."
            f"\n\n"
            f"If all else fails, delete your store directory and let the bot recreate "
            f"it (your reminders will NOT be deleted, but the bot may respond to existing "
            f"commands a second time)."
        )

        red_x_and_lock_emoji = "❌ 🔐"

        # React to the undecryptable event with some emoji
        #await react_to_event(
        #    self.client,
        #    room.room_id,
        #    event.event_id,
        #    red_x_and_lock_emoji,
        #)

    async def unknown(self, room: MatrixRoom, event: UnknownEvent) -> None:
        """Callback for when an event with a type that is unknown to matrix-nio is received.
        Currently this is used for reaction events, which are not yet part of a released
        matrix spec (and are thus unknown to nio).

        Args:
            room: The room the reaction was sent in.

            event: The event itself.
        """
        if event.type == "m.reaction":
            # Get the ID of the event this was a reaction to
            relation_dict = event.source.get("content", {}).get("m.relates_to", {})

            reacted_to = relation_dict.get("event_id")
            if reacted_to and relation_dict.get("rel_type") == "m.annotation":
                await self._reaction(room, event, reacted_to)
                return

        logger.debug(
            f"Got unknown event with type to {event.type} from {event.sender} in {room.room_id}."
        )

    async def sync(self, response):
        #print(f"We synced, token: {response.next_batch}")
        self.synced = True
