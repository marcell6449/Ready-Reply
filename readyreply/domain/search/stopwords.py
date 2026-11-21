"""Words that carry no meaning for finding an answer (stored without accents)."""

_SPANISH = """
a al algo algun alguna con de del el ella ellos en es esta estan este esto estoy hay la las le
les lo los me mi mis muy nos o para pero por que se si su sus te tiene tienen tu un una uno
unos unas y ya hola buenas buenos dias tardes noches favor gracias quiero quisiera saber usted
ustedes puedo pueden puede podria seria hacen hace tienes
"""
_ENGLISH = """
the an is are do does you your what of to for in on at and or i my can please hi hello
"""

STOP_WORDS = frozenset((_SPANISH + _ENGLISH).split())
