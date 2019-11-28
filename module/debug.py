from jishaku.cog import JishakuBase, jsk
from jishaku.metacog import GroupCogMeta


# Add Jishaku as a cog in order to hide it from the HelpCommand

class Debug(JishakuBase, metaclass=GroupCogMeta, command_parent=jsk, command_attrs=dict(hidden=True)):
    pass


def setup(bot):
    bot.add_cog(Debug(bot))
