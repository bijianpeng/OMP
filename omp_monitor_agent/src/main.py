import sys
from lib.views import app
from lib.webapp import scheduler
if __name__ == "__main__":
    try:
        try:
            scheduler.start()
            app.run(host="0.0.0.0", port=(app.config["PORT"]), access_log=False)
        except KeyboardInterrupt:
            scheduler.stop_loop()
            print("CTRL C")

    finally:
        scheduler.stop_loop()
