from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LoginResponse:
    token: str
    address: str
    alias: str
    chain: str
    perps_alpha: bool
