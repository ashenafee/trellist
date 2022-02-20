from typing import List
from trello import Card


class TList:
    """A class representing a Trello List object."""

    def __init__(self, list_id: str, name: str, closed: bool, cards: List[Card]):
        """Initialize the TList object."""
        self.list_id = list_id
        self.name = name
        self.closed = closed
        self.cards = cards

    def __str__(self):
        """Return a string representation of the TList object."""
        str_rep = f"Items for '{self.name}':"
        if self.cards:
            for card in self.cards:
                str_rep += f"\n\t{card.name}"
        else:
            str_rep += "\n\tNo cards (empty list)"
        return str_rep


if __name__ == "__main__":
    pass
