"""Start JEV HUD. No third-party dependency is needed for the server."""
from hud.config import Config
from hud.server import Application, make_server
from hud.storage import file_lock


def main():
    config = Config.from_env()
    # Acquire before constructing AlertCenter: a second server must not alter in-flight sends.
    with file_lock(config.home / 'state' / 'server', timeout=0):
        app = Application(config)
        server = make_server(app)
        app.start()
        print(f'JEV Command Center: http://127.0.0.1:{config.port}', flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            app.stop.set()
            server.server_close()


if __name__ == '__main__':
    main()
