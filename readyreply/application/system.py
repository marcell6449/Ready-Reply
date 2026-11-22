"""Phone access over the local Wi-Fi (address and QR code)."""

from readyreply.application.context import Actor
from readyreply.application.ports import NetworkInfo
from readyreply.domain.permissions import Action


class GetPhoneAccess:
    def __init__(self, network: NetworkInfo) -> None:
        self._network = network

    def url(self, actor: Actor, port: int) -> str:
        actor.require(Action.VIEW_SYSTEM)
        return f"http://{self._network.local_address()}:{port}/"

    def qr(self, actor: Actor, port: int) -> bytes:
        return self._network.qr_svg(self.url(actor, port))
