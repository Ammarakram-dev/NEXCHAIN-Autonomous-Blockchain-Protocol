from __future__ import annotations

import argparse
import json
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from urllib.parse import (
    parse_qs,
    urlparse,
)

from api.service import NEXCHAINService


MAX_BODY = 1_048_576


def json_bytes(
    payload: object,
) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class APIError(Exception):

    def __init__(
        self,
        status: int,
        message: str,
    ) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


class NEXCHAINHandler(
    BaseHTTPRequestHandler
):

    service: NEXCHAINService

    server_version = (
        "NEXCHAIN-RPC/1.0"
    )

    protocol_version = "HTTP/1.1"

    def send_json(
        self,
        status: int,
        payload: object,
    ) -> None:

        body = json_bytes(payload)

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.send_header(
            "Cache-Control",
            "no-store",
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET,POST,OPTIONS",
        )

        self.end_headers()

        if status != 204:
            self.wfile.write(body)

    def error(
        self,
        status: int,
        message: str,
    ) -> None:
        self.send_json(
            status,
            {
                "ok": False,
                "error": message,
                "status": status,
            },
        )

    def read_body(self) -> dict:

        length = int(
            self.headers.get(
                "Content-Length",
                "0",
            )
        )

        if length <= 0:
            return {}

        if length > MAX_BODY:
            raise APIError(
                413,
                "Request body is too large.",
            )

        raw = self.rfile.read(length)

        try:
            value = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise APIError(
                400,
                "Request body must be valid JSON.",
            ) from exc

        if not isinstance(
            value,
            dict,
        ):
            raise APIError(
                400,
                "Request body must be a JSON object.",
            )

        return value

    def do_OPTIONS(self) -> None:
        self.send_json(
            204,
            {},
        )

    def do_GET(self) -> None:

        try:
            parsed = urlparse(
                self.path
            )

            path = (
                parsed.path.rstrip("/")
                or "/"
            )

            query = parse_qs(
                parsed.query
            )

            # ----------------------------------------------------
            # ROOT
            # ----------------------------------------------------

            if path == "/":
                return self.send_json(
                    200,
                    {
                        "name": "NEXCHAIN",
                        "token": "NEX",
                        "api_version": "v1",
                        "health": (
                            "/api/v1/health"
                        ),
                        "status": (
                            "/api/v1/status"
                        ),
                    },
                )

            # ----------------------------------------------------
            # NETWORK
            # ----------------------------------------------------

            if path == "/api/v1/health":
                return self.send_json(
                    200,
                    self.service.health(),
                )

            if path == "/api/v1/status":
                return self.send_json(
                    200,
                    self.service.status(),
                )

            if path == "/api/v1/validate":
                return self.send_json(
                    200,
                    self.service.validate(),
                )

            # ----------------------------------------------------
            # BLOCKS
            # ----------------------------------------------------

            if path == "/api/v1/blocks":

                limit = int(
                    query.get(
                        "limit",
                        ["20"],
                    )[0]
                )

                return self.send_json(
                    200,
                    {
                        "blocks": (
                            self.service
                            .list_blocks(
                                limit
                            )
                        )
                    },
                )

            if path.startswith(
                "/api/v1/blocks/"
            ):

                value = path.split(
                    "/"
                )[-1]

                try:
                    height = int(value)
                except ValueError as exc:
                    raise APIError(
                        400,
                        "Block height must be an integer.",
                    ) from exc

                return self.send_json(
                    200,
                    self.service.get_block(
                        height
                    ),
                )

            # ----------------------------------------------------
            # TRANSACTIONS
            # ----------------------------------------------------

            if path.startswith(
                "/api/v1/transactions/"
            ):

                transaction_hash = (
                    path.split("/")[-1]
                )

                return self.send_json(
                    200,
                    self.service
                    .get_transaction(
                        transaction_hash
                    ),
                )

            # ----------------------------------------------------
            # ADDRESSES
            # ----------------------------------------------------

            if path.startswith(
                "/api/v1/addresses/"
            ):

                address = (
                    path.split("/")[-1]
                )

                return self.send_json(
                    200,
                    self.service
                    .get_address(
                        address
                    ),
                )

            # ----------------------------------------------------
            # MEMPOOL
            # ----------------------------------------------------

            if path == "/api/v1/mempool":

                return self.send_json(
                    200,
                    self.service.mempool(),
                )

            # ----------------------------------------------------
            # VALIDATORS
            # ----------------------------------------------------

            if path == "/api/v1/validators":

                return self.send_json(
                    200,
                    {
                        "validators": (
                            self.service
                            .validators()
                        )
                    },
                )

            # ----------------------------------------------------
            # WALLETS
            # ----------------------------------------------------

            if path == "/api/v1/wallets":

                return self.send_json(
                    200,
                    {
                        "wallets": (
                            self.service
                            .list_wallets()
                        )
                    },
                )

            # ----------------------------------------------------
            # CONTRACTS
            # ----------------------------------------------------

            if path == "/api/v1/contracts":

                return self.send_json(
                    200,
                    self.service.contracts(),
                )

            if (
                path.startswith(
                    "/api/v1/contracts/"
                )
                and path.endswith(
                    "/storage"
                )
            ):

                address = path.split(
                    "/"
                )[4]

                values = query.get(
                    "key"
                )

                if not values:
                    raise APIError(
                        400,
                        "Query parameter 'key' is required.",
                    )

                return self.send_json(
                    200,
                    self.service
                    .read_contract_storage(
                        address,
                        int(values[0]),
                    ),
                )

            if path.startswith(
                "/api/v1/contracts/"
            ):

                address = path.split(
                    "/"
                )[4]

                return self.send_json(
                    200,
                    self.service
                    .get_contract(
                        address
                    ),
                )

            raise APIError(
                404,
                "Endpoint not found.",
            )

        except APIError as exc:
            self.error(
                exc.status,
                exc.message,
            )

        except (
            KeyError,
            FileNotFoundError,
        ):
            self.error(
                404,
                "Resource not found.",
            )

        except ValueError as exc:
            self.error(
                400,
                str(exc),
            )

        except Exception:
            self.error(
                500,
                "Internal server error.",
            )

    def do_POST(self) -> None:

        try:
            parsed = urlparse(
                self.path
            )

            path = (
                parsed.path.rstrip("/")
                or "/"
            )

            body = self.read_body()

            # ----------------------------------------------------
            # WALLET CREATE
            # ----------------------------------------------------

            if path == "/api/v1/wallets":

                return self.send_json(
                    201,
                    self.service
                    .create_wallet(
                        str(
                            body.get(
                                "password",
                                "",
                            )
                        )
                    ),
                )

            # ----------------------------------------------------
            # WALLET IMPORT
            # ----------------------------------------------------

            if path == (
                "/api/v1/wallets/import"
            ):

                return self.send_json(
                    201,
                    self.service
                    .import_wallet(
                        str(
                            body.get(
                                "private_key",
                                "",
                            )
                        ),
                        str(
                            body.get(
                                "password",
                                "",
                            )
                        ),
                    ),
                )

            # ----------------------------------------------------
            # WALLET EXPORT
            # ----------------------------------------------------

            if (
                path.startswith(
                    "/api/v1/wallets/"
                )
                and path.endswith(
                    "/export"
                )
            ):

                address = path.split(
                    "/"
                )[4]

                return self.send_json(
                    200,
                    self.service
                    .export_wallet(
                        address,
                        str(
                            body.get(
                                "password",
                                "",
                            )
                        ),
                    ),
                )

            # ----------------------------------------------------
            # WALLET SEND
            # ----------------------------------------------------

            if (
                path.startswith(
                    "/api/v1/wallets/"
                )
                and path.endswith(
                    "/send"
                )
            ):

                address = path.split(
                    "/"
                )[4]

                nonce = body.get(
                    "nonce"
                )

                return self.send_json(
                    202,
                    self.service
                    .send_from_wallet(
                        address=address,
                        password=str(
                            body.get(
                                "password",
                                "",
                            )
                        ),
                        recipient=str(
                            body.get(
                                "recipient",
                                "",
                            )
                        ),
                        amount=float(
                            body.get(
                                "amount",
                                0,
                            )
                        ),
                        fee=float(
                            body.get(
                                "fee",
                                0.0001,
                            )
                        ),
                        nonce=(
                            None
                            if nonce is None
                            else int(nonce)
                        ),
                    ),
                )

            # ----------------------------------------------------
            # RAW TRANSACTION
            # ----------------------------------------------------

            if path == (
                "/api/v1/transactions"
            ):

                return self.send_json(
                    202,
                    self.service
                    .submit_raw_transaction(
                        body
                    ),
                )

            # ----------------------------------------------------
            # BLOCK PRODUCTION
            # ----------------------------------------------------

            if path == (
                "/api/v1/node/produce-block"
            ):

                return self.send_json(
                    201,
                    self.service
                    .produce_block(),
                )

            # ----------------------------------------------------
            # CONTRACT DEPLOYMENT
            # ----------------------------------------------------

            if path == (
                "/api/v1/contracts/deploy"
            ):

                return self.send_json(
                    201,
                    self.service
                    .deploy_contract(
                        deployer=str(
                            body.get(
                                "deployer",
                                "",
                            )
                        ),
                        program_data=dict(
                            body.get(
                                "program",
                                {},
                            )
                        ),
                        initial_storage=dict(
                            body.get(
                                "initial_storage",
                                {},
                            )
                        ),
                    ),
                )

            # ----------------------------------------------------
            # CONTRACT CALL
            # ----------------------------------------------------

            if (
                path.startswith(
                    "/api/v1/contracts/"
                )
                and path.endswith(
                    "/call"
                )
            ):

                address = path.split(
                    "/"
                )[4]

                return self.send_json(
                    200,
                    self.service
                    .call_contract(
                        address,
                        gas_limit=int(
                            body.get(
                                "gas_limit",
                                100_000,
                            )
                        ),
                        initial_stack=[
                            int(value)
                            for value in body.get(
                                "initial_stack",
                                [],
                            )
                        ],
                    ),
                )

            # ----------------------------------------------------
            # SELF TEST
            # ----------------------------------------------------

            if path == (
                "/api/v1/self-test"
            ):

                return self.send_json(
                    200,
                    self.service
                    .self_test(),
                )

            raise APIError(
                404,
                "Endpoint not found.",
            )

        except APIError as exc:
            self.error(
                exc.status,
                exc.message,
            )

        except (
            KeyError,
            FileNotFoundError,
        ):
            self.error(
                404,
                "Resource not found.",
            )

        except ValueError as exc:
            self.error(
                400,
                str(exc),
            )

        except Exception:
            self.error(
                500,
                "Internal server error.",
            )

    def log_message(
        self,
        format: str,
        *args: object,
    ) -> None:

        print(
            "[NEXCHAIN-API]",
            self.address_string(),
            "-",
            format % args,
        )


def run(
    host: str = "127.0.0.1",
    port: int = 8080,
) -> None:

    service = NEXCHAINService()

    handler = type(
        "BoundNEXCHAINHandler",
        (NEXCHAINHandler,),
        {},
    )

    handler.service = service

    server = ThreadingHTTPServer(
        (host, port),
        handler,
    )

    print("=" * 70)
    print("NEXCHAIN API / RPC")
    print("=" * 70)
    print(
        f"Listening: http://{host}:{port}"
    )
    print(
        "Health   : /api/v1/health"
    )
    print(
        "Status   : /api/v1/status"
    )
    print(
        "Explorer : /api/v1/blocks"
    )
    print(
        "Wallets  : /api/v1/wallets"
    )
    print(
        "Press Ctrl+C to stop."
    )
    print("=" * 70)

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        print(
            "\nNEXCHAIN API stopped."
        )

    finally:
        server.server_close()


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "NEXCHAIN API / RPC server"
        )
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8080,
    )

    args = parser.parse_args()

    run(
        args.host,
        args.port,
    )


if __name__ == "__main__":
    main()