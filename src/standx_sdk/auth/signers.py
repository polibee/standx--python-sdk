"""Injectable wallet-signing boundary."""


class WalletSigner:
    def __init__(self, chain: str, address: str) -> None:
        if not address.strip():
            raise ValueError("address must not be empty")
        self.chain = chain
        self.address = address

    async def sign_login_message(self, message: str) -> str:
        raise NotImplementedError("wallet implementation must sign the login message")
