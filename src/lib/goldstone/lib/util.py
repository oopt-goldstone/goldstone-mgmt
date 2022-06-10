import inspect
from aiohttp import web


async def call(f, *args, **kwargs):
    if inspect.iscoroutinefunction(f):
        return await f(*args, **kwargs)
    else:
        return f(*args, **kwargs)


async def start_probe(route, host, port):
    routes = web.RouteTableDef()

    @routes.get(route)
    async def probe(request):
        return web.Response()

    app = web.Application()
    app.add_routes(routes)

    runner = web.AppRunner(app)

    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    return runner
