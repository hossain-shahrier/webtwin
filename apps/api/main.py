import os


def get_port() -> int:
    if port := os.environ.get("PORT"):
        return int(port)
    return 8060


def main() -> None:
    import uvicorn

    port = get_port()
    print(f"API listening on http://127.0.0.1:{port}")
    uvicorn.run("api.app:app", host="127.0.0.1", port=port, reload=True)


if __name__ == "__main__":
    main()
