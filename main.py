from core.runtime import NEXCHAINRuntime


def main():
    print("=" * 70)
    print("NEXCHAIN — INTEGRATED PROTOCOL")
    print("=" * 70)

    try:
        runtime = NEXCHAINRuntime()

        print("\nRuntime initialized successfully.")
        print("Network :", "NEXCHAIN")
        print("Token   :", "NEX")
        print("Height  :", runtime.blockchain.height)
        print("Validator:", runtime.validator_address)
        print("State Root:", runtime.state.state_root())
        print("Mempool :", runtime.mempool.size)

        print("\nRunning integrated integrity test...\n")

        results = runtime.self_test()

        for name, result in results.items():
            print(
                f"[{'PASS' if result else 'FAIL'}] {name}"
            )

        print("\n" + "=" * 70)

        if results.get("overall", False):
            print("NEXCHAIN INTEGRATED RUNTIME: READY")
        else:
            print("NEXCHAIN INTEGRATED RUNTIME: CHECK FAILED")

        print("=" * 70)

    except Exception as exc:
        print("\n" + "=" * 70)
        print("NEXCHAIN STARTUP ERROR")
        print("=" * 70)
        print(type(exc).__name__ + ":", exc)
        print("=" * 70)


if __name__ == "__main__":
    main()