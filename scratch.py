import httpx
import asyncio

async def fetch():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:127.0) Gecko/20100101 Firefox/127.0',
        'Accept': 'text/event-stream',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Referer': 'https://search.vespa.ai/',
        'Origin': 'https://search.vespa.ai',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'Priority': 'u=4',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'
    }

    query = 'hello'
    filters = '+namespace:open-p +namespace:cloud-p +namespace:vespaapps-p +namespace:blog-p +namespace:pyvespa-p'
    query_profile = 'llmsearch'

    params = {
        'query': query,
        'filters': filters,
        'queryProfile': query_profile,
    }

    url = 'https://api.search.vespa.ai/stream/'

    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, headers=headers, params=params) as response:
            response.raise_for_status()
            message = ""
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[len("data: "):]
                    message += data
                    print(data, end='')  # Post each update as a message part
                elif line.startswith("event: end"):
                    print("\nEnd of message.")  # Final message post
                    break

# To run the async function, use the following code
asyncio.run(fetch())