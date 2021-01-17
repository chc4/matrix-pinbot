# Matrix-Pinbot
A Matrix bot that automatically pins chat messages to an archive channel.
This uses [nio-template](https://github.com/anoadragon453/nio-template) as a base.

Matrix doesn't natively have a Discord-like "pin" feature. This adds one: it will automatically quote any message the bot is in to the configured `pins_room` if the message is reacted to with a 📌 emoji. It will automatically join all channels it is invited to.

# Setup
 Follow SETUP.md in tree for how to set it up: notably, for me I had to set the `pins_room` config to the "Internal room ID", and not the published address.

# Problems
This uses a Matrix [rich reply](https://matrix.org/docs/spec/client_server/r0.6.1#rich-replies) to quote the original message across rooms. They render correctly on Element *mobile*, but on Element *web* show up as "Unable to load event that was replied to, it either does not exist or you do not have permission to view it." Presumably this is because Element mobile just uses the embedded_msg "fallback", while web actually implements native replies/quotes (but doesn't use the fallback if they fail...?) The spec only says that messages *SHOULD* belong to the same room, and that "Clients should be cautious of the event ID belonging to another room", so I'm just going to say tha Element web is breaking spec here.
