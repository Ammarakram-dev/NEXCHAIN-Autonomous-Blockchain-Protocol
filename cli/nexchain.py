from __future__ import annotations

import argparse
import getpass
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import (
    Request,
    urlopen,
)


DEFAULT_API = (
    "http://127.0.0.1:8080"
)


def request(
    api: str,
    method: str,
    path: str,
    payload: dict | None = None,
) -> object:

    url = (
        api.rstrip("/")
        + path
    )

    data = None

    headers = {
        "Accept": "application/json"
    }

    if payload is not None:
        data = json.dumps(
            payload
        ).encode("utf-8")

        headers[
            "Content-Type"
        ] = "application/json"

    request_object = Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:

        with urlopen(
            request_object,
            timeout=10,
        ) as response:

            raw = (
                response
                .read()
                .decode("utf-8")
            )

            return (
                json.loads(raw)
                if raw
                else {}
            )

    except HTTPError as exc:

        raw = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {
                "error": (
                    raw
                    or str(exc)
                )
            }

        print(
            json.dumps(
                payload,
                indent=2,
            )
        )

        raise SystemExit(1)

    except URLError as exc:

        print(
            "Cannot reach NEXCHAIN API:",
            exc.reason,
            file=sys.stderr,
        )

        raise SystemExit(2)


def main() -> None:

    parser = argparse.ArgumentParser(
        prog="nexchain",
        description=(
            "NEXCHAIN developer and wallet CLI"
        ),
    )

    parser.add_argument(
        "--api",
        default=DEFAULT_API,
    )

    commands = (
        parser
        .add_subparsers(
            dest="command",
            required=True,
        )
    )

    commands.add_parser(
        "health"
    )

    commands.add_parser(
        "status"
    )

    commands.add_parser(
        "validate"
    )

    blocks = commands.add_parser(
        "blocks"
    )

    blocks.add_argument(
        "--limit",
        type=int,
        default=10,
    )

    block = commands.add_parser(
        "block"
    )

    block.add_argument(
        "height",
        type=int,
    )

    transaction = commands.add_parser(
        "tx"
    )

    transaction.add_argument(
        "hash"
    )

    address = commands.add_parser(
        "address"
    )

    address.add_argument(
        "address"
    )

    commands.add_parser(
        "mempool"
    )

    commands.add_parser(
        "validators"
    )

    commands.add_parser(
        "contracts"
    )

    commands.add_parser(
        "produce-block"
    )

    commands.add_parser(
        "self-test"
    )

    wallet = commands.add_parser(
        "wallet"
    )

    wallet_commands = (
        wallet
        .add_subparsers(
            dest="wallet_command",
            required=True,
        )
    )

    wallet_commands.add_parser(
        "create"
    )

    wallet_import = (
        wallet_commands
        .add_parser("import")
    )

    wallet_import.add_argument(
        "private_key"
    )

    wallet_export = (
        wallet_commands
        .add_parser("export")
    )

    wallet_export.add_argument(
        "address"
    )

    wallet_send = (
        wallet_commands
        .add_parser("send")
    )

    wallet_send.add_argument(
        "address"
    )

    wallet_send.add_argument(
        "recipient"
    )

    wallet_send.add_argument(
        "amount",
        type=float,
    )

    wallet_send.add_argument(
        "--fee",
        type=float,
        default=0.0001,
    )

    wallet_send.add_argument(
        "--nonce",
        type=int,
    )

    args = parser.parse_args()

    if args.command == "health":

        result = request(
            args.api,
            "GET",
            "/api/v1/health",
        )

    elif args.command == "status":

        result = request(
            args.api,
            "GET",
            "/api/v1/status",
        )

    elif args.command == "validate":

        result = request(
            args.api,
            "GET",
            "/api/v1/validate",
        )

    elif args.command == "blocks":

        result = request(
            args.api,
            "GET",
            (
                "/api/v1/blocks"
                f"?limit={args.limit}"
            ),
        )

    elif args.command == "block":

        result = request(
            args.api,
            "GET",
            (
                "/api/v1/blocks/"
                f"{args.height}"
            ),
        )

    elif args.command == "tx":

        result = request(
            args.api,
            "GET",
            (
                "/api/v1/transactions/"
                f"{args.hash}"
            ),
        )

    elif args.command == "address":

        result = request(
            args.api,
            "GET",
            (
                "/api/v1/addresses/"
                f"{args.address}"
            ),
        )

    elif args.command == "mempool":

        result = request(
            args.api,
            "GET",
            "/api/v1/mempool",
        )

    elif args.command == "validators":

        result = request(
            args.api,
            "GET",
            "/api/v1/validators",
        )

    elif args.command == "contracts":

        result = request(
            args.api,
            "GET",
            "/api/v1/contracts",
        )

    elif args.command == "produce-block":

        result = request(
            args.api,
            "POST",
            "/api/v1/node/produce-block",
            {},
        )

    elif args.command == "self-test":

        result = request(
            args.api,
            "POST",
            "/api/v1/self-test",
            {},
        )

    elif args.command == "wallet":

        if args.wallet_command == "create":

            password = getpass.getpass(
                "New wallet password: "
            )

            confirmation = (
                getpass.getpass(
                    "Confirm password: "
                )
            )

            if password != confirmation:
                raise SystemExit(
                    "Passwords do not match."
                )

            result = request(
                args.api,
                "POST",
                "/api/v1/wallets",
                {
                    "password": password
                },
            )

        elif (
            args.wallet_command
            == "import"
        ):

            password = getpass.getpass(
                "Wallet password: "
            )

            result = request(
                args.api,
                "POST",
                "/api/v1/wallets/import",
                {
                    "private_key": (
                        args.private_key
                    ),
                    "password": password,
                },
            )

        elif (
            args.wallet_command
            == "export"
        ):

            password = getpass.getpass(
                "Wallet password: "
            )

            result = request(
                args.api,
                "POST",
                (
                    "/api/v1/wallets/"
                    f"{args.address}/export"
                ),
                {
                    "password": password
                },
            )

        elif (
            args.wallet_command
            == "send"
        ):

            password = getpass.getpass(
                "Wallet password: "
            )

            payload = {
                "password": password,
                "recipient": (
                    args.recipient
                ),
                "amount": (
                    args.amount
                ),
                "fee": args.fee,
            }

            if args.nonce is not None:
                payload["nonce"] = (
                    args.nonce
                )

            result = request(
                args.api,
                "POST",
                (
                    "/api/v1/wallets/"
                    f"{args.address}/send"
                ),
                payload,
            )

        else:
            raise SystemExit(
                "Unknown wallet command."
            )

    else:
        raise SystemExit(
            "Unknown command."
        )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()