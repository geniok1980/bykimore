import asyncio
from app.services.iiko_service import IikoService


async def main():
    svc = IikoService()
    names = await svc.fetch_stoplist_names()
    print("Stoplist names count:", len(names))
    print("Stoplist names sample:", names[:10])


if __name__ == "__main__":
    asyncio.run(main())