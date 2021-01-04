import discord


class Colour(discord.Colour):
    """Custom Colour class with additional colours
    taken from the game.
    """

    @classmethod
    def cyan(cls):
        return cls(0x63C1B1)

    @classmethod
    def light_blue(cls):
        return cls(0x65A3E6)

    @classmethod
    def red(cls):
        return cls(0xA62A2A)

    @classmethod
    def unvaulted_red(cls):
        return cls(0xE03D51)

    @classmethod
    def apricot(cls):
        return cls(0xE16859)
