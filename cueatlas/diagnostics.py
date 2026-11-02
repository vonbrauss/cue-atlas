"""Small rolling local stack reports when the GUI event loop stops responding."""
import faulthandler,os
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QTimer


def start(app):
    try:
        root=Path.home()/'Library'/'Logs'/'CueAtlas';root.mkdir(parents=True,exist_ok=True)
        for old in sorted(root.glob('hang-*.log'))[:-4]:old.unlink(missing_ok=True)
        path=root/(datetime.now().strftime('hang-%Y%m%d-%H%M%S-')+str(os.getpid())+'.log')
        stream=path.open('w');stream.write('Cue Atlas GUI stall reports (15 seconds without an event-loop heartbeat).\n');stream.flush()
        timer=QTimer(app);timer.setInterval(5000)
        def heartbeat():
            faulthandler.cancel_dump_traceback_later();faulthandler.dump_traceback_later(15,repeat=True,file=stream)
        def stop():
            timer.stop();faulthandler.cancel_dump_traceback_later();stream.close()
        timer.timeout.connect(heartbeat);app.aboutToQuit.connect(stop);heartbeat();timer.start()
        app._cueatlas_diagnostics=(timer,stream,path)
    except (OSError,RuntimeError):pass
