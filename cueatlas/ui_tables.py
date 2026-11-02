"""Shared table updates that defer expensive content measurements."""
from contextlib import contextmanager
from PySide6.QtWidgets import QHeaderView


@contextmanager
def batch_table_update(table):
    """Suspend content sizing too: hiding paints alone still sizes every cell."""
    header=table.horizontalHeader()
    modes=[header.sectionResizeMode(i) for i in range(table.columnCount())]
    signals=table.blockSignals(True);updates=table.updatesEnabled()
    table.setUpdatesEnabled(False)
    header.setSectionResizeMode(QHeaderView.Fixed)
    try:
        yield
    finally:
        for i,mode in enumerate(modes):header.setSectionResizeMode(i,mode)
        table.blockSignals(signals);table.setUpdatesEnabled(updates)

