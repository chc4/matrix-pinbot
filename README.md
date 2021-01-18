# Matrix-Pinbot
A Matrix bot that automatically pins chat messages to an archive channel.
This uses [nio-template](https://github.com/anoadragon453/nio-template) as a base.

Matrix doesn't natively have a Discord-like "pin" feature. This adds one: it will automatically quote any message the bot is in to the configured `pins_room` if the message is reacted to with a 📌 emoji. It will automatically join all channels it is invited to.

# Setup
 Follow SETUP.md in tree for how to set it up: notably, for me I had to set the `pins_room` config to the "Internal room ID", and not the published address.
