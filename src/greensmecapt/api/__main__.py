"""Run the GREENSMECAPT API locally."""

import uvicorn


def main() -> None:
    """Start the development API server."""

    uvicorn.run(
        "greensmecapt.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()